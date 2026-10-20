"""What the chat model is told about a review, and the maps used to check
what it cites back (ADR-0050 §3).

The model sees the stored review under short aliases: findings are F1..Fn
(most important first), a finding's own citation is C-F1, requirements and
resources by name. It never sees finding UUIDs, so it can't cite a finding
from another review: an alias that isn't in this review's map doesn't
exist.

Every string here was written by the review model from untrusted input,
so each one is normalized (stage 1) and clipped (stage 2) before it goes
into the prompt. The resource summary is ADR-0049's, which is sanitized
by construction (allowlisted settings, typed values, cleaned names).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from backend.shared.sanitize import clip, normalize_text

FIELD_CHARS = 1200
BRIEF_CHARS = 4000
TITLE_CHARS = 120
ALTERNATIVES_PER_FINDING = 3
# About 9k tokens. Over this, lower-priority findings are cut down to their
# one-line text, then dropped, rather than failing the question.
REVIEW_BLOCK_CHARS = 36000

# Same buckets as backend/shared/report.py's _PRIORITY_BY_TYPE (a test
# keeps them equal), without importing the pydantic models into the chat
# Lambda.
PRIORITY_BY_TYPE = {
    "deterministic-rule-result": "high",
    "fact": "confirmed",
    "assumption": "review",
    "inference": "review",
    "recommendation": "review",
    "not-observable": "unknown",
}
_PRIORITY_RANK = {"high": 0, "review": 1, "unknown": 2, "confirmed": 3}

NO_RESOURCES_NOTE = (
    "This review was stored before resource summaries were kept with it, so "
    "no resource settings are available. Don't describe any setting as set or "
    "missing; say it isn't determinable from this review."
)


def _text(value: Any, limit: int = FIELD_CHARS) -> str:
    return clip(normalize_text(value), limit) if isinstance(value, str) else ""


@dataclass
class ReviewContext:
    review_data: dict[str, Any]
    finding_ids: dict[str, str] = field(default_factory=dict)  # "F1" -> finding_id
    finding_titles: dict[str, str] = field(default_factory=dict)  # "F1" -> short text
    finding_categories: dict[str, str] = field(default_factory=dict)
    # "C-F1" -> the finding's stored citation: exact span, source, heading.
    finding_citations: dict[str, dict[str, str]] = field(default_factory=dict)
    resource_addresses: set[str] = field(default_factory=set)
    requirement_labels: dict[str, str] = field(default_factory=dict)
    not_observable_aliases: list[str] = field(default_factory=list)
    alternatives: list[tuple[str, str]] = field(default_factory=list)  # (alias, option)

    def alias_for(self, finding_id: str) -> str | None:
        for alias, fid in self.finding_ids.items():
            if fid == finding_id:
                return alias
        return None

    def cached_text(self) -> str:
        return json.dumps({"review_data": self.review_data}, ensure_ascii=False)


def _order(findings: list[dict]) -> list[dict]:
    indexed = list(enumerate(findings))
    indexed.sort(
        key=lambda pair: (
            _PRIORITY_RANK.get(PRIORITY_BY_TYPE.get(pair[1].get("type", ""), "review"), 1),
            -float(pair[1].get("confidence") or 0),
            pair[0],
        )
    )
    return [f for _, f in indexed]


def _compact_finding(alias: str, finding: dict, parent_alias: str | None) -> dict[str, Any]:
    alternatives = [
        {
            "option": _text(a.get("option"), 200),
            "reason_rejected": _text(a.get("reason_rejected"), 300),
        }
        for a in (finding.get("alternatives_considered") or [])[:ALTERNATIVES_PER_FINDING]
        if isinstance(a, dict)
    ]
    citation = finding.get("citation")
    compact: dict[str, Any] = {
        "ref": alias,
        "category": _text(finding.get("category"), 40),
        "type": _text(finding.get("type"), 40),
        "priority": PRIORITY_BY_TYPE.get(finding.get("type", ""), "review"),
        "finding": _text(finding.get("finding")),
        "evidence": _text(finding.get("evidence")),
        "risk_impact": _text(finding.get("risk_impact")),
        "recommendation": _text(finding.get("recommendation")),
        "alternatives_considered": alternatives,
        "confidence": round(float(finding.get("confidence") or 0), 2),
        "source": (
            {
                "ref": f"C-{alias}",
                "heading_path": _text(citation.get("heading_path"), 300),
                "quote": _text(citation.get("exact_text_span")),
            }
            if isinstance(citation, dict) and citation.get("exact_text_span")
            else None
        ),
    }
    if parent_alias:
        compact["deeper_analysis_of"] = parent_alias
    return compact


def _trim(review_data: dict[str, Any]) -> dict[str, Any]:
    """Fit the review block under REVIEW_BLOCK_CHARS: lowest-priority
    findings lose detail first, then the lowest are dropped."""

    def size() -> int:
        return len(json.dumps(review_data, ensure_ascii=False))

    findings = review_data["findings"]
    for finding in reversed(findings):
        if size() <= REVIEW_BLOCK_CHARS:
            return review_data
        for key in ("evidence", "risk_impact", "recommendation"):
            finding[key] = ""
        finding["alternatives_considered"] = []
    omitted = 0
    while findings and size() > REVIEW_BLOCK_CHARS:
        findings.pop()
        omitted += 1
    if omitted:
        review_data["omitted_findings"] = omitted
    return review_data


def build_review_context(ledger: dict[str, Any]) -> ReviewContext:
    findings = [f for f in ledger.get("findings") or [] if isinstance(f, dict)]
    ordered = _order(findings)
    aliases = {f.get("finding_id"): f"F{i}" for i, f in enumerate(ordered, start=1)}

    ctx = ReviewContext(review_data={})
    compact_findings = []
    for finding in ordered:
        alias = aliases[finding.get("finding_id")]
        ctx.finding_ids[alias] = str(finding.get("finding_id"))
        ctx.finding_titles[alias] = _text(finding.get("finding"), TITLE_CHARS)
        ctx.finding_categories[alias] = _text(finding.get("category"), 40)
        compact = _compact_finding(alias, finding, aliases.get(finding.get("parent_finding_id")))
        compact_findings.append(compact)
        citation = finding.get("citation")
        if isinstance(citation, dict) and citation.get("exact_text_span"):
            ctx.finding_citations[f"C-{alias}"] = {
                "span": str(citation["exact_text_span"]),
                "source_url": str(citation.get("source_url", "")),
                "heading_path": str(citation.get("heading_path", "")),
                "chunk_id": str(citation.get("chunk_id") or ""),
            }
        if finding.get("type") == "not-observable":
            ctx.not_observable_aliases.append(alias)
        for alternative in compact["alternatives_considered"]:
            if alternative["option"]:
                ctx.alternatives.append((alias, alternative["option"]))

    requirements = []
    for answer in ledger.get("baseline_answers") or []:
        if not isinstance(answer, dict) or not isinstance(answer.get("field"), str):
            continue
        name = answer["field"]
        ctx.requirement_labels[name] = _text(answer.get("label"), 80) or name
        requirements.append(
            {
                "ref": f"requirement:{name}",
                "label": ctx.requirement_labels[name],
                "value": _text(answer.get("value"), 300),
                "source": _text(answer.get("outcome"), 20),
            }
        )

    summary = ledger.get("terraform_resources")
    if isinstance(summary, dict) and isinstance(summary.get("resources"), list):
        resources = []
        for entry in summary["resources"]:
            if not isinstance(entry, dict):
                continue
            address = f"{entry.get('type')}.{entry.get('name')}"
            ctx.resource_addresses.add(address)
            resources.append({"ref": f"resource:{address}", **entry})
        terraform_resources: dict[str, Any] = {
            "resources": resources,
            "truncated": bool(summary.get("truncated")),
            "note": _text(summary.get("note"), 800),
        }
    else:
        terraform_resources = {"resources": [], "available": False, "note": NO_RESOURCES_NOTE}

    ctx.review_data = _trim(
        {
            "workload_brief": _text(ledger.get("workload_brief"), BRIEF_CHARS),
            "requirements": requirements,
            "findings": compact_findings,
            "terraform_resources": terraform_resources,
        }
    )
    # A finding trimmed out of the prompt can't be cited or suggested
    # either: the model never saw it.
    shown = {f["ref"] for f in ctx.review_data["findings"]}
    for alias in [a for a in ctx.finding_ids if a not in shown]:
        del ctx.finding_ids[alias]
        ctx.finding_titles.pop(alias, None)
        ctx.finding_categories.pop(alias, None)
        ctx.finding_citations.pop(f"C-{alias}", None)
    ctx.not_observable_aliases = [a for a in ctx.not_observable_aliases if a in shown]
    ctx.alternatives = [(a, o) for a, o in ctx.alternatives if a in shown]
    return ctx
