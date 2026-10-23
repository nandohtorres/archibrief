"""Who may use the chat, and the public shape of a stored question.

Shared by ask_question and list_questions, so the read-only Lambda doesn't
bundle the model-calling code.
"""

from __future__ import annotations

import os
from typing import Any

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
    return {
        "question_id": item["questionKey"].split("#", 1)[1],
        "kind": item.get("kind", "custom"),
        "suggested_id": item.get("suggestedId"),
        "question": item.get("question", ""),
        "status": item.get("status"),
        "refusal_reason": item.get("refusalReason"),
        "answer": item.get("answer") or [],
        "asked_at": item.get("askedAt"),
        "model_id": item.get("modelId"),
        "prompt_version": item.get("promptVersion"),
    }
