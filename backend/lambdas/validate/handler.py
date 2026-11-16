"""ArchiBrief Lambda: validate.

Enforces the `Finding` schema on every produced finding (ADR-0022 layer
3) — the last structural gate before a finding reaches AuditLog/Finalize.
Never accepts a raw dict; anything that fails Finding validation is
rejected with the specific error, not silently dropped.
"""

from __future__ import annotations

from pydantic import ValidationError

from backend.shared.models.finding import Finding
from backend.shared.unverified import unverified_finding, unverified_findings


def validate_findings(raw_findings: list[dict]) -> tuple[list[Finding], list[dict]]:
    valid: list[Finding] = []
    rejected: list[dict] = []

    seen = set()
    for raw in raw_findings:
        try:
            finding = Finding.model_validate(raw)
            if finding.finding_id in seen:
                rejected.append(
                    {
                        "raw": raw,
                        "errors": [{"type": "duplicate_finding"}],
                        "reason_code": "duplicate_finding",
                    }
                )
            else:
                seen.add(finding.finding_id)
                valid.append(finding)
        except (ValidationError, TypeError) as exc:
            rejected.append(
                {
                    "raw": raw,
                    "errors": exc.errors()
                    if isinstance(exc, ValidationError)
                    else [{"type": "invalid_fields"}],
                }
            )

    return valid, rejected


def handler(event, context):
    raw_findings = event["findings"]
    valid, rejected = validate_findings(raw_findings)

    unverified = unverified_findings(event.get("unverified_findings"))
    unverified.extend(
        unverified_finding(
            item["raw"],
            item.get("reason_code", "invalid_fields"),
            checks=[
                {
                    "name": "duplicate"
                    if item.get("reason_code") == "duplicate_finding"
                    else "format",
                    "status": "failed",
                }
            ],
        )
        for item in rejected
    )
    return {
        "unverified_findings": unverified,
        "disproved_findings": unverified_findings(event.get("disproved_findings")),
        "status": "complete" if not rejected else "partial",
        "valid_findings": [f.model_dump(mode="json") for f in valid],
        "rejected_count": len(rejected),
        "rejected": rejected,
    }
