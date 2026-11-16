"""Assembles the frontend's `ReviewReport` contract shape
(frontend/lib/contracts.ts) from a reviews-table pointer item and the S3
evidence ledger `finalize.handler` writes.

Used by get_review.handler for a completed review. get_demo's static
reference payload is built separately but follows the same `Finding` and
contract shapes.
"""

from __future__ import annotations

from typing import Any

from backend.shared.analysis_quality import public_analysis_quality, public_analysis_scope
from backend.shared.assessment import finding_assessment
from backend.shared.models.finding import Finding, FindingType
from backend.shared.money_policy import code_without_money, field_without_money
from backend.shared.scope_projection import public_review_scope
from backend.shared.stakeholder.presentation import brief_meta
from backend.shared.unverified import unverified_finding, unverified_findings

# Heuristic mapping that matches frontend/lib/fixtures.ts's fixtureReport
# (deterministic-rule-result -> high, fact -> confirmed, assumption ->
# review, not-observable -> unknown). Inference and recommendation go to
# "review" as the closest fit: a synthesized claim to weigh, neither a
# confirmed fact nor a rule violation. Not yet validated against a large
# sample of real model output.
_PRIORITY_BY_TYPE: dict[FindingType, tuple[str, str]] = {
    FindingType.DETERMINISTIC_RULE_RESULT: ("high", "Rule result"),
    FindingType.FACT: ("confirmed", "Reported fact"),
    FindingType.ASSUMPTION: ("review", "Review"),
    FindingType.INFERENCE: ("review", "Review"),
    FindingType.RECOMMENDATION: ("review", "Review"),
    FindingType.NOT_OBSERVABLE: ("unknown", "Not observable"),
}


def compute_presentation(finding: Finding) -> dict[str, str]:
    priority, short_label = _PRIORITY_BY_TYPE[finding.type]
    return {"priority": priority, "short_label": short_label}


def report_findings(findings: list[Finding]) -> list[dict[str, Any]]:
    entries = []
    for f in findings:
        record = f.model_dump(mode="json")
        entry = {
            "record": record,
            # Legacy display keys remain for older clients only.
            "presentation": compute_presentation(f),
            "assessment": finding_assessment(record),
        }
        # The Stakeholder Brief's presentation facts (ADR-0062). Prices and
        # the old stakeholder card are no longer sent.
        meta = brief_meta(f)
        if meta is not None:
            entry["brief"] = meta
        entries.append(entry)
    return entries


def build_review_report(review_item: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    from pydantic import ValidationError

    ledger = dict(ledger)
    failed = unverified_findings(ledger.get("unverified_findings"))
    findings = []
    seen = set()
    for raw in ledger.get("findings", []):
        try:
            finding = Finding.model_validate(raw)
            if finding.finding_id in seen:
                failed.append(
                    unverified_finding(
                        raw, "duplicate_finding", checks=[{"name": "duplicate", "status": "failed"}]
                    )
                )
            else:
                seen.add(finding.finding_id)
                findings.append(finding)
        except (ValidationError, TypeError):
            failed.append(
                unverified_finding(
                    raw, "invalid_fields", checks=[{"name": "format", "status": "failed"}]
                )
            )
    ledger["unverified_findings"] = failed

    report = {
        "review_id": review_item["reviewId"],
        # ADR-0044 removed user accounts, so there is no per-user identity.
        # The frontend's ReviewReport type still requires the field, so it
        # holds a fixed placeholder.
        "owner_id": "admin",
        "status": "complete",
        "analysis_quality": public_analysis_quality(ledger.get("analysis_quality")),
        "review_scope": public_review_scope(ledger.get("review_scope")),
        # terraformRepoRef is persisted by IdempotencyGate's PutItem
        # (infra/modules/step-functions-lambda/main.tf); costEstimateTier is
        # computed by finalize.handler.compute_cost_estimate_tier, a
        # resource-count heuristic rather than a dollar estimate. The .get()
        # fallbacks cover older review items that lack either field.
        "terraform_repo_ref": review_item.get("terraformRepoRef", "unknown (not yet persisted)"),
        "created_at": review_item.get("completedAt", ledger.get("generated_at")),
        "cost_estimate_tier": review_item.get("costEstimateTier", "medium"),
        "baseline_answers": ledger.get("baseline_answers", []),
        "findings": report_findings(findings),
        **{
            key: [
                {
                    **entry,
                    **{
                        field: (
                            code_without_money(entry[field])
                            if field == "evidence"
                            else field_without_money(entry[field])
                        )[0]
                        for field in ("finding", "evidence", "resource", "submitted_quote")
                    },
                    **{
                        side: [
                            {**ref, "text": field_without_money(ref["text"])[0]}
                            for ref in entry[side]
                        ]
                        for side in ("supporting_evidence", "contradicting_evidence")
                    },
                }
                for entry in unverified_findings(ledger.get(key))
            ]
            for key in ("unverified_findings", "disproved_findings")
        },
    }
    checks = (report["analysis_quality"].get("additional_verification") or {}).get("findings", [])
    by_id = {entry["finding_id"]: entry["status"] for entry in checks}
    for finding in report["findings"]:
        status = by_id.get(finding["record"]["finding_id"])
        if status in {"supported", "not-independently-checked", "fix-needs-confirmation"}:
            finding["independent_check"] = status
    summary = ledger.get("terraform_resources")
    scope = (
        public_analysis_scope(summary.get("analysis_coverage"))
        if isinstance(summary, dict)
        else None
    )
    if scope:
        report["analysis_scope"] = scope
    for field in ("report_projection", "deeper_reviews", "deeper_jobs"):
        if field in ledger:
            report[field] = ledger[field]
    # The architecture diagram; older ledgers don't have one.
    if isinstance(ledger.get("architecture"), dict):
        report["architecture"] = ledger["architecture"]
    return report
