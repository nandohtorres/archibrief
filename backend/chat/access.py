"""Who may use the chat, and the public shape of a stored question.

Shared by ask_question and list_questions, so the read-only Lambda doesn't
bundle the model-calling code.
"""

from __future__ import annotations

import hmac
import os
from typing import Any

DEFAULT_QUESTIONS_PER_REVIEW = 5
FINAL_STATUSES = ("answered", "not_determinable", "refused")


def is_admin(event: dict) -> bool:
    """Same constant-time comparison as the admin authorizer."""
    expected = os.environ.get("ADMIN_KEY", "")
    headers = {str(k).lower(): v for k, v in (event.get("headers") or {}).items()}
    provided = headers.get("x-admin-key", "")
    # Bytes, so a non-ASCII header can't raise (compare_digest rejects
    # non-ASCII str).
    return bool(expected) and hmac.compare_digest(
        str(provided).encode("utf-8"), expected.encode("utf-8")
    )


def caller_allowed(admin: bool) -> bool:
    """Admin only until the chat opens to the public (ADR-0050 §2). The flag
    is a second lock behind the API's admin authorizer, so removing the
    authorizer alone can't open a paid public endpoint."""
    return admin or os.environ.get("CHAT_PUBLIC_ENABLED", "false").lower() == "true"


def questions_per_review() -> int:
    try:
        return int(os.environ.get("CHAT_QUESTIONS_PER_REVIEW", DEFAULT_QUESTIONS_PER_REVIEW))
    except ValueError:
        return DEFAULT_QUESTIONS_PER_REVIEW


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
