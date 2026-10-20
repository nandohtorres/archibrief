"""The stakeholder view: each finding in plain terms, what fixing it costs
per month and in time, and what not fixing it could cost, plus a budget
summary across every finding that needs action.

Built when a report is read (backend/shared/report.py) rather than saved,
so a price-table update reaches older reports too. Everything here is
deterministic: plain-language text comes from the catalog (rule findings)
or the finding's own `plain` block (model or hand-written), and every
dollar figure comes from pricing.py.
"""

from __future__ import annotations

import re
from typing import Any

from backend.shared.models.finding import Finding, FindingType, PlainLanguage
from backend.shared.stakeholder.catalog import (
    HARMS,
    RECIPES,
    SEVERITIES,
    Harm,
    infer_concern,
)
from backend.shared.stakeholder.pricing import (
    PRICE_ITEMS,
    PRICE_REGION,
    PRICES_AS_OF,
    PricedLine,
    price_line,
)

VERDICT_LABELS: dict[str, str] = {
    "fix-today": "Fix today",
    "quick-win": "Quick win",
    "worth-the-money": "Worth the money",
    "when-budget-allows": "When budget allows",
}
_VERDICT_ORDER = list(VERDICT_LABELS)

PRICE_NOTE = (
    f"AWS list prices for {PRICE_REGION}, on-demand, as of {PRICES_AS_OF}. A real bill "
    "also depends on region, discounts, traffic and storage. Effort is a rough guide "
    "for one engineer who knows the system."
)

# What a caveat's "{item}" placeholder becomes.
_CAVEAT_PRICES = {
    key: f"about ${item.monthly:,.0f}/month" for key, item in PRICE_ITEMS.items() if item.monthly
}

_RESOURCE_REF = re.compile(r'resource "([a-z0-9_]+)" "([^"]+)"')
_QUOTED_NAME = re.compile(r"'([^']{1,80})'")
_PERCENT = re.compile(r"(\d{2}(?:\.\d+)?)\s*%")


def _verdict(severity: str, lines: list[PricedLine]) -> str:
    free = all(line.monthly_high == 0 for line in lines)
    urgent = severity in ("critical", "high")
    if free:
        return "fix-today" if urgent else "quick-win"
    return "worth-the-money" if urgent else "when-budget-allows"


def _hours_text(hours: float) -> str:
    if hours < 1:
        return f"{round(hours * 60)} minutes"
    return f"{hours:g} hour" if hours == 1 else f"{hours:g} hours"


def effort_label(low: float, high: float) -> str:
    """Hours for small jobs, working days (8 hours) for bigger ones."""
    if high <= 8:
        if low == high:
            return f"about {_hours_text(high)}"
        if high < 1:
            return f"{round(low * 60)} to {round(high * 60)} minutes"
        if low >= 1:
            return f"{low:g} to {_hours_text(high)}"
        return f"{_hours_text(low)} to {_hours_text(high)}"
    low_days, high_days = max(0.5, round(low / 4) / 2), max(0.5, round(high / 4) / 2)
    if low_days == high_days:
        return f"about {high_days:g} working day{'s' if high_days > 1 else ''}"
    return f"{low_days:g} to {high_days:g} working days"


def _resource_setting(
    finding: Finding, terraform_resources: dict | None, setting: str
) -> str | None:
    """A setting on the resource the finding's evidence names, from the
    rule engine's sanitized resource summary."""
    match = _RESOURCE_REF.search(finding.evidence)
    if not match or not isinstance(terraform_resources, dict):
        return None
    resource_type, name = match.groups()
    for entry in terraform_resources.get("resources") or []:
        if entry.get("type") == resource_type and entry.get("name") == name:
            value = (entry.get("settings") or {}).get(setting)
            return value if isinstance(value, str) else None
    return None


def _availability_target(baseline_answers: list[dict]) -> float | None:
    for answer in baseline_answers:
        if answer.get("field") == "availability_criticality":
            match = _PERCENT.search(str(answer.get("value") or ""))
            if match and 90 <= float(match.group(1)) < 100:
                return float(match.group(1))
    return None


# For a fix whose cost of not fixing fits no listed harm, so every card
# that needs action still has both cost boxes.
_UNLISTED_HARM = Harm(
    "Depends on what this part of the system protects",
    "There's no published figure that fits this finding.",
    method="Estimate what an outage or data loss in this part of the system would "
    "cost the business, and how likely it is to happen.",
)


def _harm_block(harm_key: str | None, baseline_answers: list[dict]) -> dict:
    harm: Harm = HARMS.get(harm_key or "", _UNLISTED_HARM)
    detail = harm.detail
    target = _availability_target(baseline_answers) if harm_key == "downtime" else None
    if target is not None:
        minutes = (100 - target) / 100 * 730 * 60
        allowed = f"{minutes / 60:.1f} hours" if minutes >= 120 else f"{round(minutes)} minutes"
        detail = (
            f"Your {target:g}% availability target allows about {allowed} of downtime a "
            f"month, and one failure here could use all of it. {detail}"
        )
    return {
        "headline": harm.headline,
        "detail": detail,
        "source_name": harm.source_name,
        "source_url": harm.source_url,
        "method": harm.method,
    }


def _fix_block(lines: list[PricedLine], effort: tuple[float, float], caveat: str | None) -> dict:
    return {
        "monthly_known": round(sum(line.monthly_low for line in lines), 2),
        # True when part of the cost depends on usage or an unlisted size.
        "has_unpriced": any(line.monthly_high is None for line in lines),
        "lines": [line.as_dict() for line in lines],
        "effort_hours_low": effort[0],
        "effort_hours_high": effort[1],
        "effort_label": effort_label(*effort),
        "caveat": caveat,
    }


def _block(
    *,
    source: str,
    concern: str | None,
    severity: str,
    title: str,
    analogy: str,
    what_could_happen: str,
    action: str,
    needs_action: bool,
    lines: list[PricedLine],
    effort: tuple[float, float],
    harm: str | None,
    caveat: str | None,
    baseline_answers: list[dict],
) -> dict:
    verdict = _verdict(severity, lines) if needs_action else None
    return {
        "source": source,
        "concern": concern,
        "severity": severity,
        "title": title,
        "analogy": analogy,
        "what_could_happen": what_could_happen,
        "action": action,
        "needs_action": needs_action,
        "verdict": verdict,
        "verdict_label": VERDICT_LABELS.get(verdict or ""),
        "fix": _fix_block(lines, effort, caveat) if needs_action else None,
        "inaction": _harm_block(harm, baseline_answers) if needs_action else None,
    }


def _rule_block(
    finding: Finding, terraform_resources: dict | None, baseline_answers: list[dict]
) -> dict | None:
    concern = finding.concern or infer_concern(finding.finding)
    recipe = RECIPES.get(concern or "")
    if recipe is None:
        return None
    lines = [
        price_line(
            component.item,
            component.quantity,
            _resource_setting(finding, terraform_resources, component.size_setting)
            if component.size_setting
            else None,
        )
        for component in recipe.components
    ]
    return _block(
        source="rule",
        concern=concern,
        severity=recipe.severity,
        title=recipe.title,
        analogy=recipe.analogy,
        what_could_happen=recipe.what_could_happen,
        action=recipe.action,
        needs_action=True,
        lines=lines,
        effort=recipe.effort_hours,
        harm=recipe.harm,
        caveat=recipe.caveat.format_map(_CAVEAT_PRICES) if recipe.caveat else None,
        baseline_answers=baseline_answers,
    )


def _plain_block(plain: PlainLanguage, baseline_answers: list[dict]) -> dict:
    lines = [
        price_line(component.item, component.quantity, component.size)
        for component in plain.fix_components
    ] or [price_line("none")]
    return _block(
        source=plain.written_by,
        concern=None,
        severity=plain.severity,
        title=plain.title,
        analogy=plain.analogy,
        what_could_happen=plain.what_could_happen,
        action=plain.action,
        needs_action=plain.needs_action,
        lines=lines,
        effort=(plain.effort_hours_low, plain.effort_hours_high),
        harm=plain.harm,
        caveat=None,
        baseline_answers=baseline_answers,
    )


def stakeholder_block(
    finding: Finding,
    terraform_resources: dict | None = None,
    baseline_answers: list[dict] | None = None,
) -> dict | None:
    """One finding's stakeholder card, or None when there's nothing to say
    in plain terms (the card then falls back to the finding's own text)."""
    answers = baseline_answers or []
    if finding.type == FindingType.DETERMINISTIC_RULE_RESULT:
        block = _rule_block(finding, terraform_resources, answers)
        if block is not None:
            # Rule titles quote the (sanitized) resource name, which tells
            # apart several cards with the same plain title.
            name = _QUOTED_NAME.search(finding.finding)
            block["subject"] = name.group(1) if name else None
        return block
    if finding.plain is not None:
        return {**_plain_block(finding.plain, answers), "subject": None}
    return None


def budget_summary(blocks: dict[str, dict]) -> dict:
    """The totals across every finding that needs action, cheapest and most
    urgent first."""
    actionable = [(fid, b) for fid, b in blocks.items() if b.get("needs_action")]
    recommended = [(fid, b) for fid, b in actionable if b["verdict"] != "when-budget-allows"]
    rows = sorted(
        (
            {
                "finding_id": fid,
                "title": b["title"],
                "subject": b.get("subject"),
                "severity": b["severity"],
                "verdict": b["verdict"],
                "verdict_label": b["verdict_label"],
                "monthly_known": b["fix"]["monthly_known"],
                "has_unpriced": b["fix"]["has_unpriced"],
                "effort_label": b["fix"]["effort_label"],
            }
            for fid, b in actionable
        ),
        # Most severe first; within a severity, free and cheap first.
        key=lambda row: (SEVERITIES.index(row["severity"]), _VERDICT_ORDER.index(row["verdict"])),
    )
    low = sum(b["fix"]["effort_hours_low"] for _, b in actionable)
    high = sum(b["fix"]["effort_hours_high"] for _, b in actionable)
    unpriced = sorted(
        {
            line["label"]
            for _, b in actionable
            for line in b["fix"]["lines"]
            if line["monthly_high"] is None
        }
    )
    return {
        "item_count": len(actionable),
        "free_count": sum(
            1
            for _, b in actionable
            if not b["fix"]["has_unpriced"] and not b["fix"]["monthly_known"]
        ),
        "monthly_known": round(sum(b["fix"]["monthly_known"] for _, b in actionable), 2),
        # Split so an optional extra (e.g. Shield Advanced) doesn't hide
        # what the urgent fixes cost.
        "monthly_recommended": round(sum(b["fix"]["monthly_known"] for _, b in recommended), 2),
        "recommended_has_unpriced": any(b["fix"]["has_unpriced"] for _, b in recommended),
        "monthly_optional": round(
            sum(
                b["fix"]["monthly_known"]
                for _, b in actionable
                if b["verdict"] == "when-budget-allows"
            ),
            2,
        ),
        "unpriced_items": unpriced,
        "effort_hours_low": low,
        "effort_hours_high": high,
        "effort_label": effort_label(low, high) if actionable else "none",
        "verdict_counts": {
            verdict: sum(1 for row in rows if row["verdict"] == verdict)
            for verdict in VERDICT_LABELS
        },
        "rows": rows,
        "prices_as_of": PRICES_AS_OF,
        "price_region": PRICE_REGION,
        "note": PRICE_NOTE,
    }


def build_stakeholder_view(
    findings: list[Finding],
    terraform_resources: dict | None = None,
    baseline_answers: list[dict] | None = None,
) -> dict[str, Any]:
    """{"blocks": {finding_id: card}, "budget": summary}."""
    blocks = {}
    for finding in findings:
        block = stakeholder_block(finding, terraform_resources, baseline_answers)
        if block is not None:
            blocks[finding.finding_id] = block
    return {"blocks": blocks, "budget": budget_summary(blocks)}
