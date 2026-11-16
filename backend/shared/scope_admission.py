"""Trusted operation admission for the small-workload pilot.

Only workers write this record after inventory validation. Runtime reads it
strongly consistently and binds the exact payload before starting paid work.
Lookup is not an exactly-once claim; existing job/pipeline claims still apply.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from decimal import Decimal

from botocore.exceptions import BotoCoreError, ClientError

from backend.shared.admission import AdmissionDenied, positive_setting, request_digest
from backend.shared.clients import DynamoDBClient
from backend.shared.model_request_budget import (
    MAX_REQUEST_BYTES,
    POLICY_VERSION,
    evidence_limit,
)
from backend.shared.retention import review_expires_at
from backend.shared.review_limits import SCOPE_POLICY_VERSION, scope_rejection_code

VERSION = "scope-admission@1"
HASH = re.compile(r"^[0-9a-f]{64}$")
MANIFEST_MESSAGE = (
    "This report has no usable scope manifest. Start a new review to request deeper analysis. "
    "Saved results are still available."
)


def inventory_digest(scope: dict) -> str:
    return request_digest(
        {
            "declarations": [
                {k: d[k] for k in ("address", "type", "parsed_key", "instances", "retained")}
                for d in scope["declarations"]
            ],
            "count_complete": scope["count_complete"],
            "module_gaps": scope["module_gaps"],
            "gaps_complete": scope["gaps_complete"],
            "warnings": scope["warnings"],
        }
    )


def _table() -> DynamoDBClient:
    name = os.environ.get("USAGE_COUNTERS_TABLE_NAME")
    if not name:
        raise AdmissionDenied("admission_unavailable")
    try:
        return DynamoDBClient(table_name=name)
    except (BotoCoreError, ClientError, TypeError, ValueError):
        raise AdmissionDenied("admission_unavailable") from None


def _read_operation(key: dict) -> dict:
    try:
        return _table().get_item(key, consistent=True) or {}
    except AdmissionDenied:
        raise
    except (BotoCoreError, ClientError, TypeError, ValueError):
        raise AdmissionDenied("admission_unavailable") from None


def _key(review_id: str, operation: str) -> dict:
    if not isinstance(review_id, str) or not 0 < len(review_id) <= 128:
        raise AdmissionDenied("invalid_operation")
    if operation != "initial" and not (
        isinstance(operation, str)
        and operation.startswith("deeper:")
        and 0 < len(operation[7:]) <= 128
    ):
        raise AdmissionDenied("invalid_operation")
    return {"counterKey": f"operation#{review_id}#{operation}"}


def _ceiling(operation: str) -> int:
    if operation == "initial":
        return min(400000, positive_setting("INITIAL_RESERVE_MICRO_USD", 400000))
    return min(200000, positive_setting("DEEPER_RESERVE_MICRO_USD", 200000))


def _receipt_valid(row: dict, operation: str, now: int) -> bool:
    cost = row.get("cost")
    return (
        not row.get("released")
        and _integer(row.get("ttl"))
        and row["ttl"] > now
        and _integer(cost)
        and 0 < cost <= _ceiling(operation)
        and isinstance(row.get("digest"), str)
        and HASH.fullmatch(row["digest"]) is not None
    )


def _integer(value: object) -> bool:
    return (
        type(value) is int
        or isinstance(value, Decimal)
        and value.is_finite()
        and value == int(value)
    )


def _valid_admission(row: dict, rid: str, operation: str, now: int) -> bool:
    admitted = row.get("scope_admission")
    if not isinstance(admitted, dict) or not _receipt_valid(row, operation, now):
        return False
    count, expires = admitted.get("known_y"), admitted.get("expires_at_epoch_s")
    return (
        admitted.get("version") == VERSION
        and admitted.get("scope_version") == "review_scope@1"
        and admitted.get("policy_version") == SCOPE_POLICY_VERSION
        and admitted.get("status") == "admitted"
        and admitted.get("review_id") == rid
        and admitted.get("operation") == operation
        and admitted.get("root_id") == "."
        and _integer(count)
        and 0 <= count <= 50
        and type(admitted.get("total_complete")) is bool
        and _integer(expires)
        and now < expires <= row["ttl"]
        and isinstance(admitted.get("prepared_job_id"), str)
        and 0 < len(admitted["prepared_job_id"]) <= 128
        and all(
            isinstance(admitted.get(k), str) and HASH.fullmatch(admitted[k]) is not None
            for k in ("archive_sha256", "input_digest", "inventory_sha256")
        )
        and isinstance(admitted.get("archive_version_id"), str)
        and 0 < len(admitted["archive_version_id"]) <= 1024
        and admitted["archive_version_id"] != "null"
        and isinstance(row.get("runtime_payload_sha256"), str)
        and HASH.fullmatch(row["runtime_payload_sha256"]) is not None
        and (operation != "initial" or admitted["input_digest"] == row["digest"])
    )


def eligible_parent(review_id: str, scope: object) -> dict:
    """Current admission and original scope are required for *new* deeper work."""
    code = scope_rejection_code(scope)
    if code or scope.get("status") != "final":
        raise AdmissionDenied(code or "scope_manifest_required")
    row = _read_operation(_key(review_id, "initial"))
    if not _valid_admission(row, review_id, "initial", int(time.time())):
        raise AdmissionDenied("scope_manifest_required")
    admitted = row["scope_admission"]
    if (
        admitted.get("inventory_sha256") != inventory_digest(scope)
        or admitted.get("known_y") != scope["known_y"]
        or admitted.get("total_complete") != scope["count_complete"]
        or int(admitted.get("expires_at_epoch_s", 0)) <= time.time()
    ):
        raise AdmissionDenied("scope_manifest_required")
    return admitted


def prepare_operation(
    review: dict, scope: dict, payload: dict, *, operation: str, job_id: str
) -> dict:
    """Bind an existing reservation to validated scope and a worker-built payload."""
    code = scope_rejection_code(scope)
    if code:
        raise AdmissionDenied(code)
    rid = review["reviewId"]
    now = int(time.time())
    expires = review_expires_at(review)
    parent = eligible_parent(rid, scope) if operation != "initial" else None
    archive_hash = parent["archive_sha256"] if parent else review.get("archiveSha256")
    archive_version = parent["archive_version_id"] if parent else review.get("archiveVersionId")
    input_hash = parent["input_digest"] if parent else review.get("inputDigest")
    if (
        not isinstance(archive_hash, str)
        or not HASH.fullmatch(archive_hash)
        or not isinstance(input_hash, str)
        or not HASH.fullmatch(input_hash)
        or not isinstance(archive_version, str)
        or not 0 < len(archive_version) <= 1024
        or archive_version == "null"
        or expires <= now
        or payload.get("review_id") != rid
        or not isinstance(job_id, str)
        or not 0 < len(job_id) <= 128
    ):
        raise AdmissionDenied("scope_manifest_required")
    bound = {k: v for k, v in payload.items() if k != "review_scope_ref"}
    payload_hash = request_digest(bound)
    admitted = {
        "version": VERSION,
        "scope_version": scope["version"],
        "policy_version": SCOPE_POLICY_VERSION,
        "review_id": rid,
        "operation": operation,
        "archive_sha256": archive_hash,
        "archive_version_id": archive_version,
        "input_digest": input_hash,
        "inventory_sha256": inventory_digest(scope),
        "known_y": scope["known_y"],
        "total_complete": scope["count_complete"],
        "root_id": ".",
        "expires_at_epoch_s": expires,
        "status": "admitted",
        "prepared_job_id": job_id,
    }
    table = _table()
    key = _key(rid, operation)
    row = _read_operation(key)
    expected_digest = (
        input_hash if operation == "initial" else request_digest({"finding_id": operation[7:]})
    )
    if not _receipt_valid(row, operation, now) or row.get("digest") != expected_digest:
        raise AdmissionDenied("operation_conflict")
    try:
        table.update_item(
            Key=key,
            UpdateExpression="SET scope_admission = :scope, runtime_payload_sha256 = :payload",
            ConditionExpression=(
                "digest = :digest AND attribute_not_exists(released) AND #ttl > :now "
                "AND cost = :cost AND (attribute_not_exists(runtime_payload_sha256) OR runtime_payload_sha256 = :payload)"
            ),
            ExpressionAttributeNames={"#ttl": "ttl"},
            ExpressionAttributeValues={
                ":scope": admitted,
                ":payload": payload_hash,
                ":digest": expected_digest,
                ":now": now,
                ":cost": row["cost"],
            },
        )
    except (BotoCoreError, ClientError, TypeError, ValueError):
        raise AdmissionDenied("admission_unavailable") from None
    return {**bound, "review_scope_ref": {"operation": operation, "job_id": job_id}}


@dataclass(frozen=True)
class PaidScopeContext:
    review_id: str
    operation: str
    payload_sha256: str
    expires_at: int


def check_paid_scope(state: dict, *clients: object) -> None:
    """Defend direct node calls with real adapters; injected fakes stay offline.

    Public JSON cannot supply a dataclass context or construct client adapters.
    Evaluation wrappers are inspected through their underlying adapter too.
    """
    from backend.shared.clients import (
        BedrockEmbeddingClient,
        BedrockReasoningClient,
        GuardrailsClient,
        S3VectorsClient,
    )

    def real(client: object) -> bool:
        if isinstance(
            client,
            (BedrockEmbeddingClient, BedrockReasoningClient, GuardrailsClient, S3VectorsClient),
        ):
            return True
        wrapped = getattr(client, "__dict__", {}).get("_wrapped")
        return wrapped is not None and wrapped is not client and real(wrapped)

    context = state.get("paid_scope_context")
    if context is None and not any(real(c) for c in clients):
        return
    if not isinstance(context, PaidScopeContext) or context.review_id != state.get("review_id"):
        raise AdmissionDenied("scope_manifest_required")
    from backend.shared.model_request_budget import GenerationBudget

    budget = state.get("generation_budget")
    if not isinstance(budget, GenerationBudget) or budget.operation != context.operation:
        raise AdmissionDenied("analysis_budget_unavailable")
    budget.check_deadline()
    for client in clients:
        adapter = client
        seen = set()
        while id(adapter) not in seen:
            seen.add(id(adapter))
            if isinstance(adapter, BedrockReasoningClient):
                if adapter.generation_budget is not budget:
                    raise AdmissionDenied("analysis_budget_unavailable")
                break
            adapter = getattr(adapter, "__dict__", {}).get("_wrapped")
            if adapter is None:
                break
    row = _read_operation(_key(context.review_id, context.operation))
    if (
        not _valid_admission(row, context.review_id, context.operation, int(time.time()))
        or row.get("screen_status") != "allowed"
        or context.expires_at <= time.time()
        or row.get("runtime_payload_sha256") != context.payload_sha256
    ):
        raise AdmissionDenied("operation_conflict")


def authorize_payload(payload: dict) -> PaidScopeContext:
    """Only an own-storage lookup can create the runtime's trusted context."""
    rid = payload.get("review_id")
    ref = payload.get("review_scope_ref")
    if not isinstance(ref, dict) or set(ref) != {"operation", "job_id"}:
        raise AdmissionDenied("scope_manifest_required")
    operation = ref["operation"]
    expected = (
        f"deeper:{payload.get('parent_finding_id')}"
        if payload.get("mode") == "deeper"
        else "initial"
    )
    if operation != expected or payload.get("mode", "initial") not in {"initial", "deeper"}:
        raise AdmissionDenied("operation_conflict")
    row = _read_operation(_key(rid, operation))
    admitted = row.get("scope_admission")
    now = int(time.time())
    digest = request_digest({k: v for k, v in payload.items() if k != "review_scope_ref"})
    if not isinstance(admitted, dict):
        raise AdmissionDenied("scope_manifest_required")
    if (
        not _valid_admission(row, rid, operation, now)
        or admitted.get("prepared_job_id") != ref["job_id"]
        or row.get("runtime_payload_sha256") != digest
    ):
        raise AdmissionDenied("operation_conflict")
    return PaidScopeContext(rid, operation, digest, int(admitted["expires_at_epoch_s"]))


def record_request_envelope(payload: dict, envelope: dict) -> None:
    context = authorize_payload(payload)
    seconds = payload.get("analysis_seconds", 400)
    if type(seconds) is not int or not 0 < seconds <= 400:
        raise AdmissionDenied("invalid_operation")
    deadline = min(context.expires_at, int(time.time()) + seconds)
    _table().update_item(
        Key=_key(context.review_id, context.operation),
        UpdateExpression="SET request_budget = :budget, analysis_deadline = :deadline",
        ConditionExpression="runtime_payload_sha256 = :digest AND attribute_not_exists(screen_status) AND attribute_not_exists(released)",
        ExpressionAttributeValues={
            ":budget": envelope,
            ":deadline": deadline,
            ":digest": context.payload_sha256,
        },
    )


def operation_reservation(payload: dict) -> int:
    context = authorize_payload(payload)
    return int(_read_operation(_key(context.review_id, context.operation))["cost"])


def checked_request_envelope(payload: dict, *, screened: bool = True) -> dict:
    context = authorize_payload(payload)
    row = _read_operation(_key(context.review_id, context.operation))
    envelope = row.get("request_budget")
    deep = context.operation.startswith("deeper:")
    if (
        not _valid_admission(row, context.review_id, context.operation, int(time.time()))
        or row.get("runtime_payload_sha256") != context.payload_sha256
        or not isinstance(envelope, dict)
        or envelope.get("version") != POLICY_VERSION
        or envelope.get("max_request_bytes") != MAX_REQUEST_BYTES
        or envelope.get("max_evidence_bytes") != evidence_limit(deep)
        or not _integer(envelope.get("request_bound_bytes"))
        or not 0 < envelope["request_bound_bytes"] <= MAX_REQUEST_BYTES
        or not _integer(envelope.get("cost_bound_micro_usd"))
        or not 0 < envelope["cost_bound_micro_usd"] <= row["cost"]
        or not _integer(envelope.get("input_token_bound"))
        or envelope["input_token_bound"] <= 0
        or not _integer(row.get("analysis_deadline"))
        or row["analysis_deadline"] <= time.time()
        or (screened and row.get("screen_status") != "allowed")
    ):
        raise AdmissionDenied("analysis_budget_unavailable")
    return row


def claim_input_screen(payload: dict) -> PaidScopeContext:
    checked_request_envelope(payload, screened=False)
    context = authorize_payload(payload)
    try:
        _table().update_item(
            Key=_key(context.review_id, context.operation),
            UpdateExpression="SET screen_status = :started",
            ConditionExpression="attribute_not_exists(screen_status) AND attribute_not_exists(released) AND runtime_payload_sha256 = :digest",
            ExpressionAttributeValues={":started": "started", ":digest": context.payload_sha256},
        )
    except ClientError:
        raise AdmissionDenied("input_screen_already_attempted") from None
    return context


def finish_input_screen(context: PaidScopeContext, allowed: bool) -> None:
    _table().update_item(
        Key=_key(context.review_id, context.operation),
        UpdateExpression="SET screen_status = :outcome",
        ConditionExpression="screen_status = :started AND runtime_payload_sha256 = :digest",
        ExpressionAttributeValues={
            ":started": "started",
            ":digest": context.payload_sha256,
            ":outcome": "allowed" if allowed else "blocked",
        },
    )
