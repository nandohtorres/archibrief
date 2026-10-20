"""Assembles the frontend's `ReviewReport` contract shape
(frontend/lib/contracts.ts) from a reviews-table pointer item + the S3
evidence ledger `finalize.handler` writes.

Shared between get_review.handler (a completed review) and get_demo's
static reference payload (built once, not through this assembly path,
but validated against the same `Finding`/contract shapes) — see
Work-Project-Issues-Log.md, 2026-10-01 entry, for why this didn't exist
before: get_review previously returned a thin DynamoDB pointer subset,
not the full contract the frontend actually expects.
"""

from __future__ import annotations

from typing import Any

from backend.shared.models.finding import Finding, FindingType

# First-pass heuristic (2026-10-01), not yet reviewed against real model
# output — matches every example in frontend/lib/fixtures.ts's
# fixtureReport exactly (deterministic-rule-result -> high, fact ->
# confirmed, assumption -> review, not-observable -> unknown), but
# inference/recommendation have no fixture precedent and are bucketed
# into "review" as the closest semantic fit (a synthesized claim to
# weigh, not a confirmed fact nor a raw rule violation). Revisit once
# real reasoning output exists to validate against.
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
        # ADR-0044 removed user accounts entirely — there is no real
        # per-user identity to put here. Kept only because the frontend's
        # ReviewReport TS type (predates ADR-0044) still declares the
        # field as required; a fixed placeholder, never a real identity.
        "owner_id": "admin",
        "status": "complete",
        # terraformRepoRef is persisted by IdempotencyGate's PutItem
        # (2026-10-01, see infra/modules/step-functions-lambda/main.tf)
        # — the .get() fallback stays only for review items written
        # before that fix. costEstimateTier is now computed by
        # finalize.handler.compute_cost_estimate_tier (2026-10-12) — a
        # first-pass, unvalidated resource-count heuristic, not a real
        # dollar estimate (see that function's own docstring/comment).
        # The .get() fallback here covers review items written before
        # this fix.
        "terraform_repo_ref": review_item.get("terraformRepoRef", "unknown (not yet persisted)"),
        "created_at": review_item.get("completedAt", ledger.get("generated_at")),
        "cost_estimate_tier": review_item.get("costEstimateTier", "medium"),
        "baseline_answers": ledger.get("baseline_answers", []),
        "findings": [
            {"record": f.model_dump(mode="json"), "presentation": compute_presentation(f)}
            for f in findings
        ],
    }
    # The architecture diagram, for reviews finalized from 2026-10-17 on.
    if isinstance(ledger.get("architecture"), dict):
        report["architecture"] = ledger["architecture"]
    return report
