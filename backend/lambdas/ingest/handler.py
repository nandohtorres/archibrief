"""ArchiBrief Lambda: ingest.

Bounded stateless work (ADR-0028): static-only HCL parse of submitted
Terraform. Never runs `terraform init`/`plan`/`apply`, provisioners, or
external data sources against submitted content (ADR-0027, a hard rule).

This module and everything it imports must have zero dependency capable
of shelling out to `terraform` — no `subprocess`, no terraform binary.
`hcl2` parses HCL to a plain dict without ever resolving or invoking
anything Terraform-side.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import hcl2
from hcl2.utils import SerializationOptions

from backend.shared.archive import (  # noqa: F401  (re-exported for callers/tests)
    ALLOWED_SUFFIXES,
    MAX_ARCHIVE_MEMBERS,
    MAX_MEMBER_BYTES,
    MAX_UNCOMPRESSED_BYTES,
    IngestRejected,
    extract_archive,
)
from backend.shared.clients import GuardrailsClient, S3Client
from backend.shared.terraform_scope import MODULE_FIELD, scoped_key

# with_comments=False: hcl2 defaults it to True, which attaches the raw
# text of any adjacent `//` or `/* */` comment to the block body as
# `__comments__`, where downstream code reads real attributes. That would
# carry instructions hidden in Terraform comments into application data
# (ADR-0038). `#` comments are dropped by the lexer either way. Comments
# are not part of the HCL data model, so nothing real is lost.
_SERIALIZATION_OPTIONS = SerializationOptions(strip_string_quotes=True, with_comments=False)


@dataclass
class ParsedTerraform:
    # type -> key -> body. Keys are module-scoped (backend/shared/
    # terraform_scope.py): bare name in the root module, "<module>/<name>"
    # in a subdirectory, with the module recorded in the body itself.
    resources: dict[str, dict[str, dict]] = field(default_factory=dict)
    variables: dict[str, dict] = field(default_factory=dict)
    files_parsed: list[str] = field(default_factory=list)
    not_observable: list[str] = field(default_factory=list)
    # Data sources (e.g. aws_iam_policy_document) and locals, scoped the
    # same way, so rules can resolve references like
    # data.aws_iam_policy_document.x.json or local.bucket_id (traps t02,
    # f03) instead of treating them as opaque strings.
    data: dict[str, dict[str, dict]] = field(default_factory=dict)
    locals: dict[str, object] = field(default_factory=dict)


def _module_for(path: str, root: str) -> str:
    relative = os.path.relpath(os.path.dirname(os.path.abspath(path)), root)
    return "" if relative == "." else PurePosixPath(*Path(relative).parts).as_posix()


def _scoped_body(body: object, module: str) -> object:
    if module and isinstance(body, dict):
        return {**body, MODULE_FIELD: module}
    return body


def parse_terraform_files(file_paths: list[str]) -> ParsedTerraform:
    """Parse each file statically via hcl2 — no terraform binary involved."""
    parsed = ParsedTerraform()
    directories = [os.path.dirname(os.path.abspath(p)) for p in file_paths]
    root = os.path.commonpath(directories) if directories else ""
    automatic_values: list[tuple[int, str, dict]] = []

    for index, path in enumerate(file_paths, start=1):
        with open(path, encoding="utf-8", errors="strict") as fh:
            try:
                document = json.load(fh) if path.endswith(".json") else hcl2.load(
                    fh, serialization_options=_SERIALIZATION_OPTIONS
                )
                if not isinstance(document, dict):
                    raise TypeError("configuration must be an object")
            except UnicodeDecodeError:
                raise IngestRejected(f"unsupported encoding in Terraform file {index}") from None
            except Exception as exc:  # noqa: BLE001 - all parser errors require sanitized rejection
                # Parser messages include source tokens, source lines and
                # absolute /tmp paths. Only trusted ordinals and numeric
                # locations may reach logs or workflow execution history.
                location = ""
                line, column = getattr(exc, "line", None), getattr(exc, "column", None)
                if type(line) is int and type(column) is int and line > 0 and column > 0:
                    location = f" at line {line}, column {column}"
                raise IngestRejected(f"failed to parse Terraform file {index}{location}") from None

        module = _module_for(path, root)
        basename = os.path.basename(path)
        if basename.endswith((".tfvars", ".tfvars.json")):
            if not module and basename in ("terraform.tfvars", "terraform.tfvars.json"):
                automatic_values.append((0 if basename == "terraform.tfvars" else 1, basename, document))
            elif not module and basename.endswith((".auto.tfvars", ".auto.tfvars.json")):
                automatic_values.append((2, basename, document))
            elif not module:
                parsed.not_observable.append(
                    "Non-automatic variable files were not selected; CLI -var-file inputs are not evaluated"
                )
            parsed.files_parsed.append(path)
            continue

        for resource_block in document.get("resource", []):
            for resource_type, named in resource_block.items():
                for name, body in named.items():
                    key = scoped_key(module, name)
                    parsed.resources.setdefault(resource_type, {})[key] = _scoped_body(body, module)
                    if _references_remote_module(body):
                        parsed.not_observable.append(f"{resource_type}.{key}")

        for data_block in document.get("data", []):
            for data_type, named in data_block.items():
                for name, body in named.items():
                    parsed.data.setdefault(data_type, {})[scoped_key(module, name)] = _scoped_body(
                        body, module
                    )

        for locals_block in document.get("locals", []):
            for name, value in locals_block.items():
                if name != "__is_block__":
                    parsed.locals[scoped_key(module, name)] = value

        for variable_block in document.get("variable", []):
            for name, body in variable_block.items():
                parsed.variables[scoped_key(module, name)] = body

        parsed.files_parsed.append(path)

    for _priority, _name, values in sorted(automatic_values, key=lambda entry: entry[:2]):
        for name, value in values.items():
            if name in parsed.variables:
                parsed.variables[name]["value"] = value
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
    `GUARDRAIL_ID`/`GUARDRAIL_VERSION` environment variables set by
    Terraform; the Guardrail is fixed per environment, so the state
    machine payload doesn't need to carry it. With neither source,
    the Guardrails check is skipped rather than failing.
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

    Submissions send `archive_s3_key`, the key the client uploaded its
    tarball to via create_upload's presigned POST (ADR-0045). The object
    is downloaded once to `dest_dir`, so extract_archive()'s
    path-traversal, symlink and member-count checks run on the local
    file as usual.

    `archive_path` (an existing local file) is also accepted, for tests
    and direct invocations.
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
    # containers reuse /tmp, so a fixed path would keep every previous
    # submission's files on disk.
    dest_dir = event.get("dest_dir") or tempfile.mkdtemp(prefix="archibrief-ingest-")
    try:
        return _ingest(event, workload_brief, dest_dir, guardrails_client, s3_client)
    finally:
        if not event.get("dest_dir"):
            shutil.rmtree(dest_dir, ignore_errors=True)


def _log_stage(review_id: str | None, stage: str, **fields: object) -> None:
    """One structured JSON log line per ingest stage.

    Written with print(flush=True) on purpose: a hard Lambda timeout kills
    the process without an exception, and CPython block-buffers stdout
    when it isn't a tty, so unflushed lines never reach CloudWatch. The
    last line for
    a review_id shows which stage it was stuck in. Never logs the brief,
    file contents or archive paths.
    """
    print(
        json.dumps({"lambda": "ingest", "review_id": review_id, "stage": stage, **fields}),
        flush=True,
    )


def _ingest(
    event: dict,
    workload_brief: str,
    dest_dir: str,
    guardrails_client: GuardrailsClient | None,
    s3_client: S3Client | None,
) -> dict:
    review_id = event.get("review_id")
    _log_stage(review_id, "resolve_archive")
    os.makedirs(dest_dir, exist_ok=True)
    archive_path = _resolve_archive_path(event, dest_dir, s3_client)
    _log_stage(review_id, "extract")
    try:
        extracted = extract_archive(archive_path, dest_dir)
        _log_stage(review_id, "parse_hcl", file_count=len(extracted))
        parsed = parse_terraform_files(extracted)
    except IngestRejected as exc:
        _log_stage(review_id, "rejected", reason=exc.reason)
        return {"status": "rejected", "reason": exc.reason}

    # Guardrails runs inline here and again before Reason (ADR-0033) — see
    # backend/agent/nodes/reason.py's module docstring. Only the workload
    # brief (free-text, attacker-controlled) is checked; the parsed HCL
    # itself is never natural-language content passed to a prompt-attack
    # classifier.
    guardrails_decisions: list[dict] = []
    client = _resolve_guardrails_client(event, guardrails_client)
    if client is not None:
        _log_stage(review_id, "guardrails")
        allowed = client.check(workload_brief, source="INPUT")
        _log_stage(review_id, "guardrails_done", allowed=allowed)
        guardrails_decisions.append({"stage": "ingest", "allowed": allowed})
        if not allowed:
            return {
                "status": "blocked",
                "reason": "Guardrails blocked the workload brief at ingest",
                "guardrails_decisions": guardrails_decisions,
            }

    parsed_payload = {
        "resources": parsed.resources,
        "variables": parsed.variables,
        "data": parsed.data,
        "locals": parsed.locals,
        # Paths relative to the archive root; the temp dir is deleted after.
        "files_parsed": [os.path.relpath(p, dest_dir) for p in parsed.files_parsed],
        "not_observable": parsed.not_observable,
    }
    result = {
        "status": "parsed",
        "resource_count": sum(len(names) for names in parsed.resources.values()),
        "guardrails_decisions": guardrails_decisions,
    }

    # In the deployed workflow the parsed tree goes to S3 and only a
    # reference travels through Step Functions state: a 50 MiB archive can
    # parse to far more than the 256 KiB state limit, and
    # execution history/logs would otherwise retain the user's Terraform.
    report_bucket = event.get("report_bucket")
    if review_id and report_bucket:
        key = f"parsed/{review_id}.json"
        client = s3_client or S3Client(bucket=report_bucket)
        client.put_object(key=key, body=json.dumps(parsed_payload).encode("utf-8"))
        return {**result, "parsed_s3_key": key}
    return {**result, **parsed_payload, "workload_brief": workload_brief}
