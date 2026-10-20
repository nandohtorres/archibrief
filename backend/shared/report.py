"""Assembles the frontend's `ReviewReport` contract shape
(frontend/lib/contracts.ts) from a reviews-table pointer item and the S3
evidence ledger `finalize.handler` writes.

Used by get_review.handler for a completed review. get_demo's static
reference payload is built separately but follows the same `Finding` and
contract shapes.
"""

from __future__ import annotations

from typing import Any

from backend.shared.models.finding import Finding, FindingType

# Heuristic mapping that matches frontend/lib/fixtures.ts's fixtureReport
# (deterministic-rule-result -> high, fact -> confirmed, assumption ->
# review, not-observable -> unknown). Inference and recommendation go to
# "review" as the closest fit: a synthesized claim to weigh, neither a
# confirmed fact nor a rule violation. Not yet validated against a large
# sample of real model output.
_PRIORITY_BY_TYPE: dict[FindingType, tuple[str, str]] = {
    FindingType.DETERMINISTIC_RULE_RESULT: ("high", "High risk"),
    FindingType.FACT: ("confirmed", "Confirmed"),
    FindingType.ASSUMPTION: ("review", "Review"),
    FindingType.INFERENCE: ("review", "Review"),
    FindingType.RECOMMENDATION: ("review", "Review"),
    FindingType.NOT_OBSERVABLE: ("unknown", "Not observable"),
}


def compute_presentation(finding: Finding) -> dict[str, str]:
    priority, short_label = _PRIORITY_BY_TYPE[finding.type]
    return {"priority": priority, "short_label": short_label}


def build_review_report(review_item: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    findings = [Finding.model_validate(f) for f in ledger.get("findings", [])]

    report = {
        "review_id": review_item["reviewId"],
        # ADR-0044 removed user accounts, so there is no per-user identity.
        # The frontend's ReviewReport type still requires the field, so it
        # holds a fixed placeholder.
        "owner_id": "admin",
        "status": "complete",
        # terraformRepoRef is persisted by IdempotencyGate's PutItem
        # (infra/modules/step-functions-lambda/main.tf); costEstimateTier is
        # computed by finalize.handler.compute_cost_estimate_tier, a
        # resource-count heuristic rather than a dollar estimate. The .get()
        # fallbacks cover older review items that lack either field.
        "terraform_repo_ref": review_item.get("terraformRepoRef", "unknown (not yet persisted)"),
        "created_at": review_item.get("completedAt", ledger.get("generated_at")),
        "cost_estimate_tier": review_item.get("costEstimateTier", "medium"),
        "baseline_answers": ledger.get("baseline_answers", []),
        "findings": [
            {"record": f.model_dump(mode="json"), "presentation": compute_presentation(f)}
            for f in findings
        ],
    }
    # The architecture diagram; older ledgers don't have one.
    if isinstance(ledger.get("architecture"), dict):
        report["architecture"] = ledger["architecture"]
    return report
