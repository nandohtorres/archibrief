"""answer_question under a deadline: the detect-only grounding check is
skipped when there isn't time for it (code review 2026-10-16)."""

from __future__ import annotations

import time

from backend.chat.answer import GROUNDING_WORST_SECONDS, ChatClients, answer_question
from backend.chat.context import build_review_context


class _Reasoning:
    model_id = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

    def converse_tool_cached(self, **_kwargs):
        raw = {
            "status": "answered",
            "refusal_reason": "none",
            "missing": "none",
            "paragraphs": [
                {
                    "text": "Narrow the role.",
                    "citations": [{"ref": "F1", "exact_quote": ""}],
                }
            ],
        }
        return raw, {"inputTokens": 10, "outputTokens": 10}


class _Grounding:
    def __init__(self):
        self.calls = 0

    def grounding_scores(self, source, query, answer):
        self.calls += 1
        return {"GROUNDING": 0.9, "RELEVANCE": 0.9}


def _ask(ledger, deadline):
    grounding = _Grounding()
    clients = ChatClients(reasoning=_Reasoning(), grounding=grounding)
    result = answer_question(
        build_review_context(ledger), "Why?", [], None, clients, "canary", deadline
    )
    return result, grounding


def test_grounding_runs_when_there_is_time(ledger):
    result, grounding = _ask(ledger, time.monotonic() + 60)
    assert grounding.calls == 1
    assert result.grounding == {"GROUNDING": 0.9, "RELEVANCE": 0.9}


def test_grounding_is_skipped_near_the_deadline(ledger):
    result, grounding = _ask(ledger, time.monotonic() + GROUNDING_WORST_SECONDS - 1)
    assert grounding.calls == 0
    assert result.grounding == {}
    assert result.answer.status == "answered"


def test_no_deadline_means_no_skip(ledger):
    _, grounding = _ask(ledger, None)
    assert grounding.calls == 1
