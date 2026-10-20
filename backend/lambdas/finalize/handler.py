"""ArchiBrief Lambda: finalize.

Assembles the structured HTML/JSON evidence ledger from validated
findings and writes pointers to DynamoDB + payload to S3 (400 KB item
cap — ADR-0034). The S3/DynamoDB writes go through the shared client
adapters and cannot succeed without deployed resources, but the ledger
assembly logic itself is real and independently testable.
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

# preflight.py's FieldOutcome enum has two values (UNKNOWN, PAUSED) the
# frontend's BaselineAnswer.outcome type doesn't model (only "answered" |
# "assumption" | "not-observable" | "stopped" — see frontend/lib/contracts.ts).
# Neither should actually reach a COMPLETED review in practice today
# (BASELINE_FIELD_POLICIES never assigns CANNOT_INFER, so "unknown" never
# occurs; "paused" implies needs_clarification, which routes the graph to
# END before Reason/Finalize ever run) — mapped defensively rather than
# left to KeyError if that ever changes.
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
    contract shape (frontend/lib/contracts.ts) — found missing entirely
    2026-10-01 while fixing get_review's response to actually match that
    contract (see Work-Project-Issues-Log.md)."""
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


# First-pass heuristic (2026-10-12), not yet reviewed against real cost
# data — same caveat as backend/shared/report.py's compute_presentation()
# (no fixture/production precedent to validate bucket edges against).
# Counts total resource instances across every type Ingest parsed
# (ignores remote-module-internal resources, which are correctly absent
# from `resources` since Ingest never resolves remote module sources —
# ADR-0027). Thresholds are a starting point, deliberately conservative
# (a handful of resources is "low," dozens is "medium"), meant to be
# revisited once there's real submitted-Terraform size data to calibrate
# against, not treated as a calibrated product decision.
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
        # Persisted here (2026-10-01), not anywhere in DynamoDB — no
        # Reviews-table item field carries it either (see
        # Work-Project-Issues-Log.md, same entry this fix is documented
        # in), and deeper_review.handler needs the original brief to
        # re-invoke Reason for a "go deeper" pass. S3 is already this
        # project's source of truth for full review content
        # (ADR-0007/0042), so the evidence ledger is the natural place,
        # not a new DynamoDB field.
        "workload_brief": workload_brief,
        # Also added 2026-10-01, same reasoning — the frontend's
        # ReviewReport.baseline_answers had no backend source at all
        # before this (runtime_entrypoint.py dropped preflight_fields on
        # every path except needs_clarification).
        "baseline_answers": baseline_answers or [],
        # RuleEngine's sanitized resource summary (ADR-0049), kept so the
        # report chat can answer from the same facts Reason saw (ADR-0050).
        # None for reviews finalized before 2026-10-15; the chat says so.
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
    # The report's diagram (rule_engine/architecture.py). Absent for
    # reviews finalized before 2026-10-17.
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

    # Found 2026-10-01 while wiring terraformRepoRef persistence: DynamoDB's
    # PutItem REPLACES the whole item, unlike UpdateItem — writing a
    # pointer_item built from scratch here would silently wipe out every
    # field IdempotencyGate wrote earlier in the same execution
    # (terraformRepoRef, idempotencyKey, createdAt), since this is the
    # second put_item call against the same reviewId. Fetch-and-merge
    # instead of blind overwrite.
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
