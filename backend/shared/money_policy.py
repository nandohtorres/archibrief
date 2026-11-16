"""No-monetary-estimates policy for public narrative (ADR-0062).

Generated text (model findings, chat answers, plain summaries) can carry a
price: "about $32/month", "USD 1,200", "$40-60 a month". Public responses
never publish one. Stored records and operational metering are never
changed; this only shapes what a caller sees.

frontend/lib/money-policy.ts implements the same rules, and both are checked
against tests/shared/money-policy-cases.json. Change them together.

Modes:
- field: each amount becomes "[amount removed]".
- narrative: a prose sentence stating an amount is dropped; inside ``` code
  fences only clearly monetary amounts are replaced (code mode).
- code: a bare "$" + whole number is kept (a positional variable such as
  $1); amounts with separators, decimals, a scale, a rate, a range, US$, USD
  or "dollars" are replaced.
Terraform ${...} and $NAME variables never match.
"""

from __future__ import annotations

import re
from typing import Any

MONEY_POLICY_VERSION = "no-monetary-estimates@2026-11-15"
AMOUNT_PLACEHOLDER = "[amount removed]"
REMOVED_SENTENCE = "A cost estimate was removed from this answer."

_NUM = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?"
_SCALE = r"(?:\s?(?:k|m|bn|million|billion|thousand)\b)"
_RATE = r"(?:\s?(?:/|per\s|an?\s)\s?(?:month|mo|year|yr|hour|hr|day|week|request|GB)\b)"
_RANGE = rf"(?:\s?(?:-|–|to\s)\s?(?:US\$|\$)?\s?{_NUM}{_SCALE}?)"
_MONEY = re.compile(
    "|".join(
        (
            rf"(?:US\$|\$)\s?{_NUM}{_SCALE}?{_RANGE}?{_RATE}?",
            rf"\bUSD\s?{_NUM}{_SCALE}?{_RANGE}?{_RATE}?",
            rf"\b{_NUM}{_SCALE}?\s?(?:USD|dollars?)\b",
        )
    ),
    re.IGNORECASE,
)
_BARE_DOLLAR_INTEGER = re.compile(r"\$[0-9]+")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")


def has_money(text: str) -> bool:
    return bool(_MONEY.search(text))


def field_without_money(text: str) -> tuple[str, int]:
    return _MONEY.subn(AMOUNT_PLACEHOLDER, text)


def code_without_money(text: str) -> tuple[str, int]:
    removed = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal removed
        if _BARE_DOLLAR_INTEGER.fullmatch(match.group(0)):
            return match.group(0)
        removed += 1
        return AMOUNT_PLACEHOLDER

    return _MONEY.sub(replace, text), removed


def _prose_without_money(text: str) -> tuple[str, int]:
    removed = 0
    lines: list[str] = []
    for line in text.split("\n"):
        found = len(_MONEY.findall(line))
        if not found:
            lines.append(line)
            continue
        removed += found
        kept = [s for s in _SENTENCE_BREAK.split(line) if not _MONEY.search(s)]
        if kept:
            lines.append(" ".join(kept))
    return "\n".join(lines), removed


def narrative_without_money(text: str) -> tuple[str, int]:
    removed = 0
    parts = []
    for index, part in enumerate(text.split("```")):
        cleaned, count = code_without_money(part) if index % 2 == 1 else _prose_without_money(part)
        removed += count
        parts.append(cleaned)
    if not removed:
        return text, 0
    joined = "```".join(parts)
    return (joined if joined.strip() else REMOVED_SENTENCE), removed


def public_answer(paragraphs: list[Any]) -> tuple[list[Any], int, int]:
    """A stored chat answer as the public sees it: prices removed from the
    narrative, and a cited quote that states a price omitted (never edited,
    since it is shown as the source's exact words). Returns the paragraphs,
    the amounts removed and the quotes omitted."""
    removed = omitted = 0
    public: list[Any] = []
    for paragraph in paragraphs:
        if not isinstance(paragraph, dict) or not isinstance(paragraph.get("text"), str):
            public.append(paragraph)
            continue
        text, count = narrative_without_money(paragraph["text"])
        removed += count
        citations = []
        for citation in paragraph.get("citations") or []:
            quote = citation.get("quote") if isinstance(citation, dict) else None
            if isinstance(quote, str) and has_money(quote):
                omitted += 1
                citation = {**citation, "quote": "", "quote_omitted": "monetary-amount"}
            citations.append(citation)
        entry = {**paragraph, "text": text, "citations": citations}
        if count:
            entry["amounts_removed"] = count
        public.append(entry)
    return public, removed, omitted
