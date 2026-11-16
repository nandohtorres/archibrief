"""Who may use the chat, and the public shape of a stored question.

Shared by ask_question and list_questions, so the read-only Lambda doesn't
bundle the model-calling code.
"""

from __future__ import annotations

import os
from typing import Any

from backend.shared.money_policy import MONEY_POLICY_VERSION, public_answer

DEFAULT_QUESTIONS_PER_REVIEW = 5
FINAL_STATUSES = ("answered", "not_determinable", "refused")


def caller_allowed() -> bool:
    """Chat opens with public access (ADR-0050 §2). The API has no
    authorizer, so this flag is the gate."""
    return os.environ.get("CHAT_PUBLIC_ENABLED", "false").lower() == "true"


def questions_per_review() -> int:
    try:
        return int(os.environ.get("CHAT_QUESTIONS_PER_REVIEW", DEFAULT_QUESTIONS_PER_REVIEW))
    except ValueError:
        return DEFAULT_QUESTIONS_PER_REVIEW


def question_is_live(item: dict[str, Any], now: float) -> bool:
    """TTL cleanup is asynchronous; malformed/missing expiry fails closed."""
    try:
        return int(item.get("ttl", 0)) > now
    except (TypeError, ValueError, OverflowError):
        return False


def transcript_item(item: dict[str, Any]) -> dict[str, Any]:
    """A stored question as the public sees it. Every chat response (new,
    replayed, a stored suggested answer) and the transcript reader go
    through here, so the no-cost-estimates policy (ADR-0062) applies to old
    saved answers too. The stored item and its metering fields are not
    changed."""
    answer, removed, omitted = public_answer(item.get("answer") or [])
    return {
        "question_id": item["questionKey"].split("#", 1)[1],
        "kind": item.get("kind", "custom"),
        "suggested_id": item.get("suggestedId"),
        "question": item.get("question", ""),
        "status": item.get("status"),
        "refusal_reason": item.get("refusalReason"),
        "answer": answer,
        "asked_at": item.get("askedAt"),
        "model_id": item.get("modelId"),
        "prompt_version": item.get("promptVersion"),
        "narrative_policy": {
            "version": MONEY_POLICY_VERSION,
            "amounts_removed": removed,
            "quotes_omitted": omitted,
        },
    }
