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

import copy
import json
import os
import re
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
from backend.shared.hcl_eval import ResolutionBudgetExceeded, resolve
from backend.shared.review_scope import (
    MAX_ADDRESS_LENGTH,
    MAX_DECLARATIONS,
    MAX_GAPS,
    new_declaration,
    pending_record,
)
from backend.shared.terraform_scope import MODULE_FIELD, display_name, scoped_key

# with_comments=False: hcl2 defaults it to True, which attaches the raw
# text of any adjacent `//` or `/* */` comment to the block body as
# `__comments__`, where downstream code reads real attributes. That would
# carry instructions hidden in Terraform comments into application data
# (ADR-0038). `#` comments are dropped by the lexer either way. Comments
# are not part of the HCL data model, so nothing real is lost.
_SERIALIZATION_OPTIONS = SerializationOptions(strip_string_quotes=True, with_comments=False)
MAX_MODULE_EXPANSION_BYTES = 50 * 1024 * 1024


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
    module_evaluation: str = ""
    # Only region configuration is retained, never provider credentials.
    providers: dict[str, dict] = field(default_factory=dict)
    # The pending P0 review scope (backend/shared/review_scope.py): what the
    # archive declares, counted from the real archive root.
    review_scope: dict | None = None


_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+$")
MAX_COPIES = 1000


class _Inventory:
    """Declarations and unread module calls, counted before any cloning.

    Only addresses, types, keys and fixed reason codes are kept; no source
    text, attribute values or file paths.
    """

    def __init__(self) -> None:
        self.declarations: list[dict] = []
        self.gaps: dict[str, list[str]] = {}
        self.reached: set[str] = set()
        self.count_complete = True
        self.gaps_complete = True
        self.malformed = False

    def _address_ok(self, address: str, *names: str) -> bool:
        if len(address) > MAX_ADDRESS_LENGTH or not all(_IDENTIFIER.fullmatch(n) for n in names):
            self.malformed = True
            return False
        return True

    def declare(self, prefix: str, resource_type: str, name: str, parsed_key: str) -> None:
        address = f"{prefix}.{resource_type}.{name}" if prefix else f"{resource_type}.{name}"
        if not self._address_ok(address, resource_type, name):
            return
        if len(self.declarations) >= MAX_DECLARATIONS:
            self.count_complete = False
            return
        # parsed_key is the key Ingest inserts the body under, after the
        # reused-module suffix is chosen; never rebuilt from the address.
        self.declarations.append(new_declaration(address, resource_type, parsed_key, None, True))

    def gap(self, address: str, reason: str) -> None:
        if not self._address_ok(address):
            return
        if address in self.gaps:
            if reason not in self.gaps[address]:
                self.gaps[address].append(reason)
            return
        if len(self.gaps) >= MAX_GAPS:
            self.gaps_complete = False
            return
        self.gaps[address] = [reason]


def _call_address(prefix: str, name: str) -> str:
    return f"{prefix}.module.{name}" if prefix else f"module.{name}"


def _instances(body: object, parsed: ParsedTerraform, module: str) -> int | None:
    """Known instance count from count/for_each, or None. Never guessed."""
    if not isinstance(body, dict):
        return None
    try:
        if "count" in body:
            value = resolve(body["count"], vars(parsed), module, _budget=[1 << 20])
            if isinstance(value, str) and value.isdigit():
                value = int(value)
            known = type(value) is int and 0 <= value <= MAX_COPIES
            return value if known else None
        if "for_each" in body:
            value = resolve(body["for_each"], vars(parsed), module, _budget=[1 << 20])
            if isinstance(value, (dict, list)) and len(value) <= MAX_COPIES:
                return len(value)
            return None
    except Exception:  # noqa: BLE001 - an unresolvable count is unknown, not an error
        return None
    return 1


def _module_for(path: str, root: str) -> str:
    relative = os.path.relpath(os.path.dirname(os.path.abspath(path)), root)
    return "" if relative == "." else PurePosixPath(*Path(relative).parts).as_posix()


def _scoped_body(body: object, module: str) -> object:
    if module and isinstance(body, dict):
        return {**body, MODULE_FIELD: module}
    return body


def parse_terraform_files(
    file_paths: list[str],
    archive_root: str | None = None,
    skipped_tf_json: list[str] | tuple[str, ...] = (),
) -> ParsedTerraform:
    """Parse each file statically via hcl2 — no terraform binary involved.

    `archive_root` is the real top of the extracted archive. Only the review
    scope inventory uses it; the legacy parse still infers its root from the
    files, unchanged. `skipped_tf_json` names the general .tf.json members
    the extractor dropped, relative to the archive root.
    """
    parsed = ParsedTerraform()
    # Per source directory, the first repeated resource or module-call name.
    # Recorded before the inserts below overwrite one of them; rejected only
    # if that source is reached from the root (P0 contract, rule 9).
    duplicates: dict[str, str] = {}
    seen_resources: dict[str, set[tuple[str, str]]] = {}
    directories = [os.path.dirname(os.path.abspath(p)) for p in file_paths]
    root = os.path.commonpath(directories) if directories else ""
    automatic_values: list[tuple[int, str, dict]] = []
    module_calls: dict[str, dict[str, dict]] = {}
    config_directories: set[str] = set()

    for index, path in enumerate(file_paths, start=1):
        with open(path, encoding="utf-8", errors="strict") as fh:
            try:
                document = (
                    json.load(fh)
                    if path.endswith(".json")
                    else hcl2.load(fh, serialization_options=_SERIALIZATION_OPTIONS)
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
                automatic_values.append(
                    (0 if basename == "terraform.tfvars" else 1, basename, document)
                )
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
                    seen = seen_resources.setdefault(module, set())
                    if (resource_type, name) in seen:
                        duplicates.setdefault(module, "duplicate_resource")
                    seen.add((resource_type, name))
                    key = scoped_key(module, name)
                    parsed.resources.setdefault(resource_type, {})[key] = _scoped_body(body, module)
        config_directories.add(module)
        for block in document.get("provider", []):
            for kind, body in block.items():
                if kind != "aws" or not isinstance(body, dict):
                    continue
                alias = body.get("alias")
                if alias is not None and not isinstance(alias, str):
                    continue
                name = "aws" + (f".{alias}" if alias else "")
                key = scoped_key(module, name)
                region = body.get("region", "${unresolved.provider_region}")
                if key in parsed.providers:
                    region = "${unresolved.duplicate_provider}"
                parsed.providers[key] = {"region": region, MODULE_FIELD: module}
                # Kept for the environment and data-classification labels
                # the rule engine reads from them (declared_context).
                default_tags = _first_block(body.get("default_tags"))
                if isinstance(default_tags, dict) and isinstance(
                    _first_block(default_tags.get("tags")), dict
                ):
                    parsed.providers[key]["default_tags"] = _first_block(default_tags["tags"])
        for block in document.get("module", []):
            existing = module_calls.setdefault(module, {})
            if isinstance(block, dict) and any(name in existing for name in block):
                duplicates.setdefault(module, "duplicate_module_call")
            existing.update(block)

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
    roots_match = archive_root is not None and os.path.normcase(
        os.path.abspath(archive_root)
    ) == os.path.normcase(root)
    inventory = _Inventory() if roots_match and "" in config_directories else None
    result = _evaluate_modules(parsed, module_calls, config_directories, root, inventory)
    result.review_scope = _review_scope(result, inventory, duplicates, skipped_tf_json)
    return result


def _review_scope(
    result: ParsedTerraform,
    inventory: _Inventory | None,
    duplicates: dict[str, str],
    skipped_tf_json: list[str] | tuple[str, ...],
) -> dict:
    """The pending record, or a rejection for a duplicate in a reached source."""
    if inventory is None:
        # No root configuration at the real archive root (nested-only or
        # independent slices): no counts, the review proceeds unchanged.
        return pending_record("unknown_root")
    for source in sorted(inventory.reached):
        if source in duplicates:
            raise IngestRejected(
                "configuration declares the same resource or module twice",
                code="malformed_configuration",
                detail=duplicates[source],
            )
    if inventory.malformed:
        return pending_record("malformed")
    warnings = []
    for member in skipped_tf_json:
        directory = PurePosixPath(member).parent.as_posix()
        if ("" if directory == "." else directory) in inventory.reached:
            warnings.append("skipped_tf_json")
    for entry in inventory.declarations:
        body = result.resources.get(entry["type"], {}).get(entry["parsed_key"])
        entry["retained"] = body is not None
        module = body.get(MODULE_FIELD, "") if isinstance(body, dict) else ""
        entry["instances"] = _instances(body, result, module) if body is not None else None
    return pending_record(
        "recorded",
        inventory.declarations,
        [{"address": a, "reasons": r} for a, r in inventory.gaps.items()],
        count_complete=inventory.count_complete and not warnings,
        gaps_complete=inventory.gaps_complete,
        warnings=warnings,
    )


def _first_block(value: object) -> object:
    """python-hcl2 gives a nested block as a one-item list."""
    return value[0] if isinstance(value, list) and value else value


def _evaluate_modules(
    raw: ParsedTerraform,
    calls: dict,
    directories: set[str],
    root: str,
    inventory: _Inventory | None = None,
) -> ParsedTerraform:
    """Walk only explicit, local singleton calls; unsupported work is disclosed.

    Reuses the same bounded resolver as the rules. Never initializes a
    module or fetches its source. Expansion has global and path bounds.
    """
    if "" not in directories:
        raw.module_evaluation = "independent-slices"
        raw.not_observable.append(
            "No root configuration is present: directories are independent static slices, "
            "not evidence that their resources are deployed together"
        )
        return raw
    result = ParsedTerraform(
        files_parsed=raw.files_parsed,
        not_observable=raw.not_observable[:],
        module_evaluation="calls",
    )
    root_path = Path(root).resolve()
    visited = 0
    resource_total = 0
    expanded_bytes = 0
    byte_sizes: dict[int, int] = {}
    omitted = object()
    used_scopes: set[str] = set()

    def gap(name: str, reason: str) -> None:
        result.not_observable.append(
            f"Module '{display_name(name)}': {reason}; contents not evaluated"
        )

    def unread(address: str, reason: str) -> None:
        if inventory is not None and address:
            inventory.gap(address, reason)

    def provably_disabled(call: dict, scope: str) -> bool:
        """Known count = 0 or empty for_each: not a gap (contract, rule 7)."""
        try:
            if "count" in call:
                count = resolve(call["count"], vars(result), scope, _budget=[1 << 20])
                return type(count) is int and count == 0
            if "for_each" in call:
                each = resolve(call["for_each"], vars(result), scope, _budget=[1 << 20])
                return each == {} or each == []
        except Exception:  # noqa: BLE001 - unknown means it may be enabled
            return False
        return False

    def clone(value: object, scope: str, *, cache: bool = True) -> object:
        nonlocal expanded_bytes
        if not cache or id(value) not in byte_sizes:
            size = len(json.dumps(value))
            if cache:
                byte_sizes[id(value)] = size
        else:
            size = byte_sizes[id(value)]
        if expanded_bytes + size > MAX_MODULE_EXPANSION_BYTES:
            gap(scope, "static expansion byte budget exceeded")
            return omitted
        expanded_bytes += size
        return copy.deepcopy(value)

    def input_value(value: object, scope: str) -> object:
        nonlocal expanded_bytes
        available = MAX_MODULE_EXPANSION_BYTES - expanded_bytes
        budget = [available]
        try:
            resolved = resolve(value, vars(result), scope, _budget=budget)
        except ResolutionBudgetExceeded:
            expanded_bytes = MAX_MODULE_EXPANSION_BYTES
            gap(scope, "static input resolution byte budget exceeded")
            return "${unresolved.module_input}"
        expanded_bytes += available - budget[0]
        return resolved

    def instantiate(
        source: str,
        scope: str,
        inputs: dict,
        ancestry: tuple[str, ...],
        inherited: dict,
        address: str = "",
    ) -> None:
        nonlocal visited
        visited += 1
        if visited > 64 or len(ancestry) > 6 or resource_total >= 1000:
            gap(scope, "static expansion budget exceeded")
            unread(address, "depth_limit" if len(ancestry) > 6 else "expansion_limit")
            return
        if source in ancestry:
            gap(scope, "cyclic local module calls")
            unread(address, "cycle")
            return
        used_scopes.add(scope)
        if inventory is not None:
            # Headers first, before any cloning, so a clone failure below
            # can't remove declarations from the count (contract, rule 8).
            inventory.reached.add(source)
            for kind, bodies in raw.resources.items():
                for key in bodies:
                    if key.rpartition("/")[0] == source:
                        name = key.rsplit("/", 1)[-1]
                        inventory.declare(address, kind, name, scoped_key(scope, name))
        bindings = dict(inherited)
        if not bind_scope(source, scope, inputs, bindings):
            # Traversal of this source stopped early: every child call not
            # yet entered is an unread module, unless provably disabled.
            for name, call in calls.get(source, {}).items():
                if not (isinstance(call, dict) and provably_disabled(call, scope)):
                    unread(_call_address(address, name), "expansion_limit")
            return
        walk_calls(source, scope, bindings, ancestry, address)

    def bind_scope(source: str, scope: str, inputs: dict, bindings: dict) -> bool:
        """Clone the source's variables, locals, providers, resources and
        data into `scope`. False when a budget stopped it early."""
        nonlocal resource_total
        for key, body in raw.variables.items():
            if key.rpartition("/")[0] == source:
                name = key.rsplit("/", 1)[-1]
                effective = {**body, **({"value": inputs[name]} if name in inputs else {})}
                bound = clone(effective, scope, cache=False)
                if bound is omitted:
                    return False
                result.variables[scoped_key(scope, name)] = bound
        for key, value in raw.locals.items():
            if key.rpartition("/")[0] == source:
                value = clone(value, scope)
                if value is omitted:
                    return False
                result.locals[scoped_key(scope, key.rsplit("/", 1)[-1])] = value
        for key, body in raw.providers.items():
            if key.rpartition("/")[0] == source:
                name = key.rsplit("/", 1)[-1]
                provider_key = scoped_key(scope, name)
                cloned = clone(body, scope)
                if cloned is omitted:
                    return False
                result.providers[provider_key] = {**cloned, MODULE_FIELD: scope}
                bindings[name] = provider_key
        for field_name in ("resources", "data"):
            for kind, bodies in getattr(raw, field_name).items():
                for key, body in bodies.items():
                    if key.rpartition("/")[0] != source:
                        continue
                    if resource_total >= 1000:
                        gap(scope, "static resource budget exceeded")
                        return False
                    resource_total += 1
                    name = key.rsplit("/", 1)[-1]
                    cloned = clone(body, scope)
                    if cloned is omitted:
                        return False
                    cloned[MODULE_FIELD] = scope
                    provider = cloned.get("provider", "aws")
                    if isinstance(provider, str):
                        provider = provider.removeprefix("${").removesuffix("}").strip()
                    cloned["__provider_binding__"] = (
                        bindings.get(provider) if isinstance(provider, str) else None
                    )
                    if scope:
                        # Provider inheritance/mapping is not evaluated. It
                        # cannot prove a shared account/region default.
                        cloned["__module_provider_unknown__"] = True
                    getattr(result, field_name).setdefault(kind, {})[scoped_key(scope, name)] = (
                        cloned
                    )
        return True

    def walk_calls(
        source: str, scope: str, bindings: dict, ancestry: tuple[str, ...], address: str
    ) -> None:
        for name, call in calls.get(source, {}).items():
            call_name = scoped_key(scope, name)
            call_address = _call_address(address, name)
            if not isinstance(call, dict):
                gap(call_name, "unsupported module declaration")
                unread(call_address, "source_unresolved")
                continue
            if "count" in call:
                count = input_value(call["count"], scope)
                if type(count) is int and count == 0:
                    continue
                if type(count) is not int or count != 1:
                    gap(call_name, "module count is unresolved or not singleton")
                    unread(
                        call_address,
                        "count_not_singleton" if type(count) is int else "count_unresolved",
                    )
                    continue
            if "for_each" in call:
                each = input_value(call["for_each"], scope)
                if each == {} or each == []:
                    continue
                gap(call_name, "module for_each instances are not evaluated")
                unread(call_address, "for_each_unsupported")
                continue
            source_value = call.get("source")
            if (
                not isinstance(source_value, str)
                or not source_value.startswith(("./", "../"))
                or "${" in source_value
                or "%{" in source_value
            ):
                gap(call_name, "remote or unresolved module source unavailable")
                remote = (
                    isinstance(source_value, str)
                    and "${" not in source_value
                    and "%{" not in source_value
                )
                unread(call_address, "remote_source" if remote else "source_unresolved")
                continue
            target = (root_path / source / source_value).resolve()
            if target != root_path and root_path not in target.parents:
                gap(call_name, "module source outside submitted archive")
                unread(call_address, "source_outside_archive")
                continue
            relative = target.relative_to(root_path).as_posix()
            relative = "" if relative == "." else relative
            if relative not in directories:
                gap(call_name, "local module files missing")
                unread(call_address, "source_missing")
                continue
            bound_inputs = {}
            for input_name, value in call.items():
                if input_name in (
                    "source",
                    "version",
                    "count",
                    "for_each",
                    "providers",
                    "depends_on",
                ) or input_name.startswith("__"):
                    continue
                resolved = input_value(value, scope)
                if "${" in json.dumps(resolved):
                    gap(call_name, "input value unresolved in parent scope")
                    resolved = "${unresolved.module_input}"
                bound_inputs[input_name] = resolved
            child_scope = relative
            attempt = 0
            while child_scope in used_scopes:
                attempt += 1
                child_scope = scoped_key(f"{call_name}_{attempt}", relative)
            result.not_observable.append(
                f"Module '{display_name(call_name)}': static provider mapping does not establish deployed account identity"
            )
            child_bindings = {"aws": bindings["aws"]} if "aws" in bindings else {}
            if "providers" in call:
                child_bindings = {}
                mapping = call["providers"]
                if isinstance(mapping, dict):
                    for local, parent in mapping.items():
                        if isinstance(parent, str):
                            parent = parent.removeprefix("${").removesuffix("}").strip()
                            if (
                                re.fullmatch(r"aws(?:\.[A-Za-z0-9_-]+)?", str(local))
                                and parent in bindings
                            ):
                                child_bindings[local] = bindings[parent]
            instantiate(
                relative,
                child_scope,
                bound_inputs,
                (*ancestry, source),
                child_bindings,
                call_address,
            )

    instantiate("", "", {}, (), {})
    return result


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
    version = event.get("archive_s3_version")
    archive_bytes = (
        client.get_object(archive_s3_key, version_id=version)
        if version
        else client.get_object(archive_s3_key)
    )

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
    skipped_tf_json: list[str] = []
    try:
        extracted = extract_archive(archive_path, dest_dir, skipped_tf_json)
        _log_stage(review_id, "parse_hcl", file_count=len(extracted))
        parsed = parse_terraform_files(
            extracted, archive_root=dest_dir, skipped_tf_json=skipped_tf_json
        )
    except IngestRejected as exc:
        _log_stage(review_id, "rejected", reason=exc.reason, code=exc.code)
        rejection = {"status": "rejected", "reason": exc.reason}
        if exc.code:
            rejection.update(code=exc.code, detail=exc.detail)
        return rejection

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
        "providers": parsed.providers,
        # Paths relative to the archive root; the temp dir is deleted after.
        "files_parsed": [os.path.relpath(p, dest_dir) for p in parsed.files_parsed],
        "not_observable": parsed.not_observable,
        "module_evaluation": parsed.module_evaluation,
        # Pending P0 record; the rule engine hands it to the worker unchanged.
        "review_scope": parsed.review_scope,
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
