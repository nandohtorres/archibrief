"""Stage 7: one structured log line per chat request (ADR-0050 §9).

Only the fields listed here are ever written, so question and answer text
can't end up in the logs by accident. A blocked question is identified by
a hash of its normalized text, never the text. Logging must never break a
response, so failures are swallowed.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import sys
from typing import Any

LOG_FIELDS = (
    "event",
    "request_id",
    "review_id",
    "kind",
    "outcome",
    "status",
    "refusal_reason",
    "error",
    "failure",
    "blocked_filters",
    "question_sha256",
    "citations_total",
    "citations_dropped",
    "retrieved_chunks",
    "grounding_score",
    "relevance_score",
    "input_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "output_tokens",
    "est_cost_micro_usd",
    "reserve_micro_usd",
    "latency_ms",
    "model_id",
    "prompt_version",
    "canary_hit",
)


def question_hash(question: str) -> str:
    return hashlib.sha256(question.encode("utf-8")).hexdigest()


def log_chat_event(**fields: Any) -> None:
    # Logging never fails a request.
    with contextlib.suppress(Exception):
        record = {key: fields[key] for key in LOG_FIELDS if key in fields}
        record.setdefault("event", "chat_question")
        sys.stdout.write(json.dumps(record, default=str) + "\n")
