"""ArchiBrief Lambda: validate.

Enforces the `Finding` schema on every produced finding (ADR-0022 layer
3) — the last structural gate before a finding reaches AuditLog/Finalize.
Never accepts a raw dict; anything that fails Finding validation is
rejected with the specific error, not silently dropped.
"""

from __future__ import annotations

from pydantic import ValidationError

from backend.shared.models.finding import Finding
from backend.shared.unverified import MAX_UNVERIFIED, unverified_finding, unverified_findings


def validate_findings(raw_findings: list[dict]) -> tuple[list[Finding], list[dict]]:
    valid: list[Finding] = []
    rejected: list[dict] = []

    for raw in raw_findings:
        try:
            valid.append(Finding.model_validate(raw))
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
    unverified.extend(unverified_finding(item["raw"], "invalid_fields") for item in rejected)
    return {
        "unverified_findings": unverified[:MAX_UNVERIFIED],
        "status": "complete" if not rejected else "partial",
        "valid_findings": [f.model_dump(mode="json") for f in valid],
        "rejected_count": len(rejected),
        "rejected": rejected,
    }
