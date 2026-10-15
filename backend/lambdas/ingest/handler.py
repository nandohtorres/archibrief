"""ArchiBrief Lambda: ingest.

Bounded stateless work (ADR-0028): static-only HCL parse of submitted
Terraform. Never runs `terraform init`/`plan`/`apply`, provisioners, or
external data sources against submitted content (ADR-0027, hard rule —
see Work-Project-Coding-Conventions.md "Security-relevant conventions").

This module and everything it imports must have zero dependency capable
of shelling out to `terraform` — no `subprocess`, no terraform binary.
`hcl2` parses HCL to a plain dict without ever resolving or invoking
anything Terraform-side.
"""

from __future__ import annotations

import os
import shutil
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath

import hcl2
from hcl2.utils import SerializationOptions

from backend.shared.clients import GuardrailsClient, S3Client

# with_comments=False (2026-10-01 fix): hcl2's SerializationOptions
# defaults with_comments to True, which attaches a `__comments__` key
# (containing the comment's raw text) onto any block with an adjacent
# `//`/`/* */` comment — found while writing the ADR-0038 adversarial
# regression suite's "instructions hidden in Terraform comments" test,
# which failed against the real parser: a `//` comment survived verbatim
# into parse_terraform_files' output (stored under the resource's body
# dict, same place RuleEngine/downstream code reads real attributes from)
# even though a `#` comment did not. `#` comments are a different lexer
# token hcl2 drops outright regardless of this option; only `//`/`/* */`
# were ever actually at risk. This option doesn't change what Terraform
# *data* gets parsed — comments were never part of the semantic HCL model
# — it only stops hcl2's own debug/tooling metadata from being carried
# into application data.
_SERIALIZATION_OPTIONS = SerializationOptions(strip_string_quotes=True, with_comments=False)

MAX_ARCHIVE_MEMBERS = 500
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_MEMBER_BYTES = 5 * 1024 * 1024
ALLOWED_SUFFIXES = {".tf", ".tfvars", ".hcl"}


class IngestRejected(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass
class ParsedTerraform:
    resources: dict[str, dict[str, dict]] = field(default_factory=dict)
    variables: dict[str, dict] = field(default_factory=dict)
    files_parsed: list[str] = field(default_factory=list)
    not_observable: list[str] = field(default_factory=list)


def _reject_unsafe_member(member: tarfile.TarInfo) -> None:
    name = member.name
    if name.startswith("/") or ".." in PurePosixPath(name).parts:
        raise IngestRejected(f"path traversal in archive member: {name}")
    if member.issym() or member.islnk():
        raise IngestRejected(f"symlink/hardlink not allowed: {name}")
    if member.isdev():
        raise IngestRejected(f"device file not allowed: {name}")
    if member.size > MAX_MEMBER_BYTES:
        raise IngestRejected(f"archive member too large: {name}")


def extract_archive(archive_path: str, dest_dir: str) -> list[str]:
    """Extract a submitted Terraform archive, statically, with no code execution.

    Rejects path traversal, symlink escapes, archive bombs, oversized
    members, and non-text file types outside the allowlist.
    """
    extracted: list[str] = []
    total_uncompressed = 0

    with tarfile.open(archive_path, mode="r:*") as archive:
        # Iterate rather than getmembers(): limits are enforced as each
        # header is read, so an archive with a huge member count is
        # rejected at member 501 instead of after scanning every header.
        members: list[tarfile.TarInfo] = []
        for member in archive:
            members.append(member)
            if len(members) > MAX_ARCHIVE_MEMBERS:
                raise IngestRejected("archive contains too many members")
            _reject_unsafe_member(member)
            total_uncompressed += max(member.size, 0)
            if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                raise IngestRejected("archive exceeds uncompressed size limit")

        for member in members:
            if not member.isfile():
                continue
            suffix = PurePosixPath(member.name).suffix
            if suffix not in ALLOWED_SUFFIXES:
                continue
            archive.extract(member, path=dest_dir, filter="data")
            extracted.append(os.path.join(dest_dir, member.name))

    if not extracted:
        raise IngestRejected("archive contained no .tf/.tfvars/.hcl files")
    return extracted


def parse_terraform_files(file_paths: list[str]) -> ParsedTerraform:
    """Parse each file statically via hcl2 — no terraform binary involved."""
    parsed = ParsedTerraform()

    for path in file_paths:
        with open(path, encoding="utf-8", errors="strict") as fh:
            try:
                document = hcl2.load(fh, serialization_options=_SERIALIZATION_OPTIONS)
            except UnicodeDecodeError as exc:
                raise IngestRejected(f"unsupported encoding in {path}") from exc
            except Exception as exc:  # hcl2 raises plain Exception/LarkError on bad syntax
                raise IngestRejected(f"failed to parse {path}: {exc}") from exc

        for resource_block in document.get("resource", []):
            for resource_type, named in resource_block.items():
                for name, body in named.items():
                    parsed.resources.setdefault(resource_type, {})[name] = body
                    if _references_remote_module(body):
                        parsed.not_observable.append(f"{resource_type}.{name}")

        for variable_block in document.get("variable", []):
            for name, body in variable_block.items():
                parsed.variables[name] = body

        parsed.files_parsed.append(path)

    return parsed


def _references_remote_module(body: dict) -> bool:
    source = body.get("source") if isinstance(body, dict) else None
    if not isinstance(source, str):
        return False
    return source.startswith(
        ("git::", "github.com", "registry.terraform.io", "http://", "https://")
    )


def _resolve_guardrails_client(
    event: dict, guardrails_client: GuardrailsClient | None
) -> GuardrailsClient | None:
    """Injected client wins (tests); otherwise build one from config.

    Checks the event payload first, then falls back to the Lambda's own
    `GUARDRAIL_ID`/`GUARDRAIL_VERSION` environment variables (set by
    Terraform once a real Bedrock Guardrail is deployed) — the deployed
    Guardrail is fixed per environment, not something the Step Functions
    state machine's payload needs to carry on every invocation. Absent
    both sources, Guardrails is skipped rather than failing — the same
    "blocked on a deployed resource, not on missing code" pattern as the
    Audit/Finalize Lambdas' DynamoDB/S3 writes.
    """
    if guardrails_client is not None:
        return guardrails_client
    guardrail_id = event.get("guardrail_id") or os.environ.get("GUARDRAIL_ID")
    guardrail_version = event.get("guardrail_version") or os.environ.get("GUARDRAIL_VERSION")
    if guardrail_id and guardrail_version:
        return GuardrailsClient(guardrail_id=guardrail_id, guardrail_version=guardrail_version)
    return None


def _resolve_archive_path(event: dict, dest_dir: str, s3_client: S3Client | None = None) -> str:
    """Resolves the local filesystem path extract_archive() needs.

    Added 2026-10-12 (ADR-0045, direct-upload archive_path design) — the
    real submission path now sends `archive_s3_key`, the key the client
    already uploaded its tarball to via create_upload's presigned POST,
    not a local path (no client could ever supply a path meaningful
    inside this Lambda's own ephemeral filesystem, which is what the
    pre-existing `archive_path` field alone would have required). Downloads
    the object once to `dest_dir` and returns that local path so
    extract_archive()'s existing, already-tested
    path-traversal/symlink/member-count checks run completely unchanged
    on the downloaded file.

    `archive_path` support is kept for direct/lower-level invocations
    (tests, and any future caller that already has a local file) — not
    deprecated, just no longer the only way in.
    """
    archive_path = event.get("archive_path")
    if archive_path:
        return archive_path

    archive_s3_key = event.get("archive_s3_key")
    if not archive_s3_key:
        raise KeyError("event must supply either archive_path or archive_s3_key")

    report_bucket = event["report_bucket"]
    client = s3_client or S3Client(bucket=report_bucket)
    archive_bytes = client.get_object(archive_s3_key)

    local_path = os.path.join(dest_dir, "archive.tar")
    with open(local_path, "wb") as f:
        f.write(archive_bytes)
    return local_path


def handler(
    event,
    context,
    guardrails_client: GuardrailsClient | None = None,
    s3_client: S3Client | None = None,
):
    workload_brief = event["workload_brief"]
    # A fresh directory per invocation, removed afterwards: warm Lambda
    # containers reuse /tmp, so a fixed path kept every previous
    # submission's files on disk (Codex F14).
    dest_dir = event.get("dest_dir") or tempfile.mkdtemp(prefix="archibrief-ingest-")
    try:
        return _ingest(event, workload_brief, dest_dir, guardrails_client, s3_client)
    finally:
        if not event.get("dest_dir"):
            shutil.rmtree(dest_dir, ignore_errors=True)


def _ingest(
    event: dict,
    workload_brief: str,
    dest_dir: str,
    guardrails_client: GuardrailsClient | None,
    s3_client: S3Client | None,
) -> dict:

    # Temporary stage-tracing (2026-10-12): this handler had zero logging,
    # so a hard Lambda timeout (process killed, no exception, no traceback)
    # gave no way to tell which of resolve/extract/parse/guardrails-check
    # was actually stuck. flush=True is required, not optional — the first
    # attempt at this tracing (no flush) produced ZERO log output on a
    # real timeout, confirming CPython block-buffers stdout when it isn't
    # a tty, and a hard Lambda timeout kills the process before that
    # buffer ever gets flushed. print() with flush=True goes to CloudWatch
    # immediately — remove once the real hang is found and fixed; not
    # meant as permanent instrumentation.
    print("ingest: resolving archive path", flush=True)
    os.makedirs(dest_dir, exist_ok=True)
    archive_path = _resolve_archive_path(event, dest_dir, s3_client)
    print(f"ingest: archive resolved to {archive_path}, extracting", flush=True)
    try:
        extracted = extract_archive(archive_path, dest_dir)
        print(f"ingest: extracted {len(extracted)} file(s), parsing HCL", flush=True)
        parsed = parse_terraform_files(extracted)
        print("ingest: HCL parsed", flush=True)
    except IngestRejected as exc:
        return {"status": "rejected", "reason": exc.reason}

    # Guardrails runs inline here and again before Reason (ADR-0033) — see
    # backend/agent/nodes/reason.py's module docstring. Only the workload
    # brief (free-text, attacker-controlled) is checked; the parsed HCL
    # itself is never natural-language content passed to a prompt-attack
    # classifier.
    guardrails_decisions: list[dict] = []
    client = _resolve_guardrails_client(event, guardrails_client)
    if client is not None:
        print("ingest: calling bedrock ApplyGuardrail", flush=True)
        allowed = client.check(workload_brief, source="INPUT")
        print(f"ingest: ApplyGuardrail returned allowed={allowed}", flush=True)
        guardrails_decisions.append({"stage": "ingest", "allowed": allowed})
        if not allowed:
            return {
                "status": "blocked",
                "reason": "Guardrails blocked the workload brief at ingest",
                "guardrails_decisions": guardrails_decisions,
            }

    return {
        "status": "parsed",
        "resources": parsed.resources,
        "variables": parsed.variables,
        "files_parsed": parsed.files_parsed,
        "not_observable": parsed.not_observable,
        "workload_brief": workload_brief,
        "guardrails_decisions": guardrails_decisions,
    }
