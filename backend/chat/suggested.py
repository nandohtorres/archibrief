"""Suggested questions, built from the report without a model (ADR-0050 §6).

Each is answered the first time someone clicks it, stored, and served
free after that. They don't use one of a review's five questions. The
text is a fixed template filled with already-stored, normalized report
text, so the same review always gets the same suggestions and ids.
"""

from __future__ import annotations

from backend.chat.context import ReviewContext

# Alternatives are stored as sentences ("Accept IMDSv1 because..."). After
# "Why not", a leading imperative verb reads better lowercased; anything
# else (AWS, Aurora, CloudFront) keeps its capital.
_LEADING_VERBS = frozenset(
    [
        "accept",
        "add",
        "adopt",
        "allow",
        "apply",
        "avoid",
        "block",
        "build",
        "choose",
        "consolidate",
        "deploy",
        "disable",
        "drop",
        "enable",
        "expose",
        "keep",
        "leave",
        "limit",
        "make",
        "merge",
        "migrate",
        "move",
        "open",
        "put",
        "rely",
        "remove",
        "replace",
        "restrict",
        "reuse",
        "run",
        "share",
        "skip",
        "split",
        "store",
        "switch",
        "trust",
        "turn",
        "use",
    ]
)


def _clip_words(text: str, limit: int) -> str:
    """Cut at a word boundary, marking the cut, so a title never ends in
    the middle of a word ("configurati…")."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    space = cut.rfind(" ")
    if space > limit // 2:
        cut = cut[:space]
    return cut.rstrip(" ,;:-") + "…"


def _as_option(text: str) -> str:
    option = _clip_words(text.rstrip(". "), 60)
    first, _, rest = option.partition(" ")
    if first.lower() in _LEADING_VERBS and first[:1].isupper():
        option = first.lower() + (" " + rest if rest else "")
    return option


def suggested_questions(ctx: ReviewContext) -> list[dict[str, str | None]]:
    """[{"id", "question", "focus"}], where focus is a finding alias or None."""
    suggestions: list[dict[str, str | None]] = [
        {"id": "s1", "question": "Which issues should I fix first, and why?", "focus": None}
    ]
    if "F1" in ctx.finding_titles:
        top = _clip_words(ctx.finding_titles["F1"], 80)
        suggestions.append(
            {
                "id": "s2",
                "question": f'Explain "{top}" for a non-technical stakeholder.',
                "focus": "F1",
            }
        )
        suggestions.append({"id": "s3", "question": f'How do I fix "{top}"?', "focus": "F1"})
    if ctx.not_observable_aliases:
        suggestions.append(
            {"id": "s4", "question": "What couldn't this review determine?", "focus": None}
        )
    if "expected_traffic_scale" in ctx.requirement_labels:
        suggestions.append(
            {"id": "s5", "question": "What changes if traffic grows 10×?", "focus": None}
        )
    if ctx.alternatives:
        alias, option = ctx.alternatives[0]
        suggestions.append(
            {"id": "s6", "question": f"Why not {_as_option(option)}?", "focus": alias}
        )
    return suggestions


def find_suggestion(ctx: ReviewContext, suggestion_id: str) -> dict[str, str | None] | None:
    for suggestion in suggested_questions(ctx):
        if suggestion["id"] == suggestion_id:
            return suggestion
    return None
