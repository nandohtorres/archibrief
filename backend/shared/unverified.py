"""Bounded, non-actionable record of claims that failed review checks.

This is deliberately not a Finding. It cannot carry fixes, citations, severity,
plain actions or arbitrary source fields into reports or model context.
"""

from __future__ import annotations

import re
import uuid

MAX_UNVERIFIED = 24
REASONS = {
    "chunk_not_retrieved": "The cited passage was not in the retrieved guidance.",
    "quote_not_in_chunk": "The quotation did not match the retrieved guidance.",
    "quote_missing": "The finding did not provide a quotation to check.",
    "chunk_missing": "The finding did not identify its source passage.",
    "citation_on_uncited_type": "The source reference did not match this finding type.",
    "rule_type_from_model": "The model labelled its claim as a deterministic rule result.",
    "invalid_type": "The finding failed the format check.",
    "invalid_fields": "The finding failed the format check.",
    "wrong_fix": "The proposed fix did not address the stated problem.",
    "unsupported_remediation": "The proposed fix did not pass the safety and applicability check.",
    "remediation_contradiction": "The claim or proposed fix conflicts with the declared configuration.",
    "rule_owned_remediation": "The proposed fix conflicts with the rule-owned guidance.",
    "contradicted": "The additional check found that the claim contradicted the supplied evidence.",
    "other": "The finding could not be confirmed by the review checks.",
}
_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_RESOURCE = re.compile(r"\b(?:aws|data\.aws)_[A-Za-z0-9_]+\.[A-Za-z0-9_-]+\b")


def _text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(c for c in value[:limit] if c.isprintable() or c in "\n\t").strip()


def unverified_finding(raw: object, reason_code: str) -> dict:
    item = raw if isinstance(raw, dict) else {}
    code = reason_code if isinstance(reason_code, str) and reason_code in REASONS else "other"
    fid = _text(item.get("finding_id"), 128)
    match = _RESOURCE.search(
        _text(item.get("finding"), 1200) + " " + _text(item.get("evidence"), 1600)
    )
    category = item.get("category")
    concern = _text(item.get("concern"), 128)
    return {
        "finding_id": fid if _ID.fullmatch(fid) else "unverified-" + str(uuid.uuid4()),
        "finding": _text(item.get("finding"), 1200)
        or "A proposed finding failed the format check.",
        "evidence": _text(item.get("evidence"), 1600),
        "resource": match.group(0) if match else _text(item.get("resource"), 160),
        "category": category
        if isinstance(category, str)
        and category
        in {"iam", "exposure", "encryption", "availability", "recovery", "observability", "cost"}
        else None,
        "concern": concern if _ID.fullmatch(concern) else None,
        "reason_code": code,
        "reason": REASONS[code],
        "recommendation_withheld": True,
    }


def unverified_findings(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [
        unverified_finding(item, item.get("reason_code", "other"))
        for item in value[:MAX_UNVERIFIED]
        if isinstance(item, dict)
    ]
