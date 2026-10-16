"""Suggested questions, built from the report without a model (ADR-0050 §6).

Each is answered the first time someone clicks it, stored, and served
free after that. They don't use one of a review's five questions. The
text is a fixed template filled with already-stored, normalized report
text, so the same review always gets the same suggestions and ids.
"""

from __future__ import annotations

from backend.chat.context import ReviewContext
from backend.shared.sanitize import clip


def suggested_questions(ctx: ReviewContext) -> list[dict[str, str | None]]:
    """[{"id", "question", "focus"}], where focus is a finding alias or None."""
    suggestions: list[dict[str, str | None]] = [
        {"id": "s1", "question": "Which issues should I fix first, and why?", "focus": None}
    ]
    if "F1" in ctx.finding_titles:
        top = clip(ctx.finding_titles["F1"], 80)
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
        suggestions.append({"id": "s6", "question": f"Why not {clip(option, 60)}?", "focus": alias})
    return suggestions


def find_suggestion(ctx: ReviewContext, suggestion_id: str) -> dict[str, str | None] | None:
    for suggestion in suggested_questions(ctx):
        if suggestion["id"] == suggestion_id:
            return suggestion
    return None
