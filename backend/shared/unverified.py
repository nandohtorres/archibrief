"""Bounded, non-actionable record of claims that failed review checks.

This is deliberately not a Finding. It cannot carry fixes, citations, severity,
plain actions or arbitrary source fields into reports or model context.
"""

from __future__ import annotations

import re
import uuid

MAX_UNVERIFIED = 24  # Legacy page size; never a storage or publication limit.
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
    "model_limit": "This claim exceeded the number of model findings checked in this pass.",
    "duplicate_finding": "This repeats another finding; it is retained separately for traceability.",
    "duplicate_finding_id": "Repeated finding identifiers prevented an independent check.",
    "verification_failed": "The independent check did not finish.",
    "insufficient_evidence": "The independent check could not establish this claim.",
    "missing_verdict": "The independent check returned no verdict for this claim.",
    "duplicate_verdict": "The independent check returned conflicting repeated verdicts.",
    "invalid_verdict": "The independent verdict did not pass its validation checks.",
    "malformed_response": "The independent response could not be validated.",
    "candidate_limit": "This claim could not be independently checked within the call limit.",
    "request_size": "This claim could not be independently checked within the request size limit.",
    "citation_integrity": "The supplied citation did not pass the source-integrity check.",
    "unattributed_scan": "The scan result could not be attributed to this resource instance.",
    "incomplete_batch": "The saved deeper result is incomplete and could not be confirmed.",
    "fix_not_applicable": "The detection may be right, but its proposed fix did not pass the safety check.",
    "parent_unverified": "This saved finding depends on a parent that is not in the verified section.",
    "other": "The finding could not be confirmed by the review checks.",
}
_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_RESOURCE = re.compile(r"\b(?:aws|data\.aws)_[A-Za-z0-9_]+\.[A-Za-z0-9_-]+\b")


def _text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(c for c in value[:limit] if c.isprintable() or c in "\n\t").strip()


def evidence_reference(identifier: str, kind: str, text: object) -> dict:
    import json

    value = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False, default=str)
    return {
        "id": _text(identifier, 160),
        "kind": kind
        if isinstance(kind, str) and kind in {"fact", "passage", "submitted-quote"}
        else "fact",
        "text": _text(value, 2000),
        "truncated": len(value) > 2000,
    }


def _references(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [
        {
            **evidence_reference(v.get("id", ""), v.get("kind", "fact"), v.get("text", "")),
            "truncated": v.get("truncated") is True
            or (isinstance(v.get("text"), str) and len(v["text"]) > 2000),
        }
        for v in value
        if isinstance(v, dict)
    ]


def _checks(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    names = {
        "format",
        "citation",
        "remediation",
        "verification",
        "attribution",
        "duplicate",
        "limit",
    }
    return [
        {"name": v["name"], "status": v["status"]}
        for v in value
        if isinstance(v, dict)
        and isinstance(v.get("name"), str)
        and v["name"] in names
        and isinstance(v.get("status"), str)
        and v.get("status") in {"passed", "failed", "not-run"}
    ]


def unverified_finding(
    raw: object,
    reason_code: str,
    *,
    checks: list | None = None,
    supporting: list | None = None,
    contradicting: list | None = None,
) -> dict:
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
        "disposition": "disproved" if code == "contradicted" else "unable-to-verify",
        "checks": _checks(checks),
        "supporting_evidence": _references(supporting),
        "contradicting_evidence": _references(contradicting),
        "submitted_quote": _text(item.get("exact_quote"), 2000),
    }


def unverified_findings(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [
        unverified_finding(
            item,
            item.get("reason_code", "other"),
            checks=item.get("checks"),
            supporting=item.get("supporting_evidence"),
            contradicting=item.get("contradicting_evidence"),
        )
        | {"submitted_quote": _text(item.get("submitted_quote"), 2000)}
        for item in value
        if isinstance(item, dict)
    ]
