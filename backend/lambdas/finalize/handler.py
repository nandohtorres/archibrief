"""ArchiBrief Lambda: finalize.

Assembles the JSON evidence ledger from validated findings, writes it to
S3, and merges a small pointer item into the review's DynamoDB record.
The full payload stays in S3 because of DynamoDB's 400 KB item cap
(ADR-0034).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from backend.agent.nodes.preflight import FIELD_LABELS
from backend.shared.architecture_links import link_findings
from backend.shared.clients import DynamoDBClient, S3Client
from backend.shared.models.finding import Finding

MAX_DYNAMODB_ITEM_BYTES = 400 * 1024

# preflight.py's FieldOutcome has two values (UNKNOWN, PAUSED) that the
# frontend's BaselineAnswer.outcome (frontend/lib/contracts.ts) doesn't
# model. Neither should reach a completed review (no policy assigns
# CANNOT_INFER, and "paused" ends the graph before Reason/Finalize), but
# they are mapped defensively rather than left to raise KeyError.
_OUTCOME_TO_CONTRACT = {
    "answered": "answered",
    "assumption": "assumption",
    "unknown": "not-observable",
    "paused": "not-observable",
    "stopped": "stopped",
}


def assemble_baseline_answers(
    preflight_fields: dict[str, Any], defaults_version: str | None
) -> list[dict[str, Any]]:
    """Converts preflight_node's internal field_state shape
    (backend/agent/nodes/preflight.py) into the frontend's BaselineAnswer
    contract shape (frontend/lib/contracts.ts)."""
    answers = []
    for field_name, field_state in preflight_fields.items():
        answers.append(
            {
                "field": field_name,
                "label": FIELD_LABELS.get(field_name, field_name),
                "outcome": _OUTCOME_TO_CONTRACT.get(field_state.get("outcome"), "not-observable"),
                "value": field_state.get("value") or "",
                "policy_version": defaults_version or "unknown",
            }
        )
    return answers


# A rough size heuristic, not a dollar estimate: counts resource instances
# across every type Ingest parsed (resources inside remote modules are
# absent because Ingest never resolves remote sources, ADR-0027). The
# thresholds are conservative starting points (a handful is "low", dozens
# "medium"), not yet calibrated against real submissions.
_COST_TIER_LOW_MAX = 5
_COST_TIER_MEDIUM_MAX = 20


def compute_cost_estimate_tier(
    resources: dict[str, dict[str, dict]] | None, resource_count: int | None = None
) -> str:
    if resource_count is None:
        resource_count = sum(len(names) for names in (resources or {}).values())
    if resource_count <= _COST_TIER_LOW_MAX:
        return "low"
    if resource_count <= _COST_TIER_MEDIUM_MAX:
        return "medium"
    return "high"


def assemble_evidence_ledger(
    review_id: str,
    findings: list[Finding],
    workload_brief: str | None = None,
    baseline_answers: list[dict[str, Any]] | None = None,
    terraform_resources: dict[str, Any] | None = None,
) -> dict[str, Any]:
    by_category: dict[str, list[dict]] = {}
    for f in findings:
        by_category.setdefault(f.category.value, []).append(f.model_dump(mode="json"))

    return {
        "review_id": review_id,
        # deeper_review.handler needs the original brief to re-invoke
        # Reason. S3 is the source of truth for full review content
        # (ADR-0007/0042), so it lives in the ledger, not in DynamoDB.
        "workload_brief": workload_brief,
        # Source of the frontend's ReviewReport.baseline_answers.
        "baseline_answers": baseline_answers or [],
        # RuleEngine's sanitized resource summary (ADR-0049), kept so the
        # report chat can answer from the same facts Reason saw (ADR-0050).
        # None in older ledgers; the chat says so.
        "terraform_resources": terraform_resources,
        "generated_at": datetime.now(UTC).isoformat(),
        "finding_count": len(findings),
        "findings_by_category": by_category,
        "findings": [f.model_dump(mode="json") for f in findings],
    }


def place_findings(graph: object, findings: list[Finding]) -> dict | None:
    """RuleEngine's graph with the final findings placed on it, or None
    when there is no graph or placing fails (the report then has no
    diagram, nothing else changes)."""
    if not isinstance(graph, dict):
        return None
    try:
        return link_findings(graph, [f.model_dump(mode="json") for f in findings])
    except Exception as exc:  # noqa: BLE001 - any failure just drops the diagram
        print(json.dumps({"event": "architecture_failed", "error": type(exc).__name__}))
        return None


def handler(event, context):
    review_id = event["review_id"]
    findings = [Finding.model_validate(f) for f in event["findings"]]
    baseline_answers = assemble_baseline_answers(
        event.get("preflight_fields") or {}, event.get("defaults_version")
    )
    ledger = assemble_evidence_ledger(
        review_id,
        findings,
        event.get("workload_brief"),
        baseline_answers,
        event.get("terraform_resources"),
    )
    # The report's diagram (rule_engine/architecture.py), when there is one.
    architecture = place_findings(event.get("architecture"), findings)
    if architecture is not None:
        ledger["architecture"] = architecture

    report_bucket = event.get("report_bucket")
    reviews_table = event.get("reviews_table_name")

    payload_key = f"reports/{review_id}/evidence-ledger.json"
    if report_bucket:
        S3Client(bucket=report_bucket).put_object(
            key=payload_key, body=json.dumps(ledger).encode("utf-8")
        )

    # PutItem replaces the whole item, so a pointer item built from scratch
    # would wipe the fields IdempotencyGate wrote earlier in the execution
    # (terraformRepoRef, idempotencyKey, createdAt). Fetch and merge instead.
    dynamodb_client = DynamoDBClient(table_name=reviews_table) if reviews_table else None
    existing_item = dynamodb_client.get_item({"reviewId": review_id}) if dynamodb_client else None

    pointer_item = {
        **(existing_item or {}),
        "reviewId": review_id,
        "status": "complete",
        "reportS3Key": payload_key,
        "findingCount": ledger["finding_count"],
        "completedAt": ledger["generated_at"],
        "costEstimateTier": compute_cost_estimate_tier(
            event.get("resources"), event.get("resource_count")
        ),
    }
    if len(json.dumps(pointer_item).encode("utf-8")) > MAX_DYNAMODB_ITEM_BYTES:
        raise ValueError("review pointer item exceeds DynamoDB 400 KB item cap")

    if dynamodb_client:
        dynamodb_client.put_item(pointer_item)

    return {
        "status": "complete",
        "report_s3_key": payload_key,
        "finding_count": ledger["finding_count"],
    }
