"""The paid chat eval's wiring, run free on a fake model, so a paid run
can't fail on plumbing (ADR-0050 §8)."""

from __future__ import annotations

from backend.chat import chat_eval
from backend.chat.answer import ChatClients


class _FakeReasoning:
    model_id = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

    def converse_tool_cached(self, **kwargs):
        return {
            "status": "answered",
            "refusal_reason": "none",
            "missing": "none",
            "paragraphs": [
                {
                    "text": "Fix the role.",
                    "citations": [{"ref": "F1", "exact_quote": ""}],
                }
            ],
        }, {"inputTokens": 100, "outputTokens": 20}


def test_quality_and_trap_runs_produce_every_metric():
    clients = ChatClients(reasoning=_FakeReasoning())
    quality = chat_eval.run_quality(clients, "canary", None)
    assert set(quality["metrics"]) >= {
        "status_accuracy",
        "citation_recall",
        "citation_integrity",
        "refusal_correctness",
        "false_refusal",
        "mean_cost_usd",
        "p95_latency_ms",
    }
    assert len(quality["rows"]) == 24
    traps = chat_eval.run_traps(clients, "canary", None)
    assert 0 <= traps["metrics"]["trap_pass_rate"] <= 1
    # A model that always answers fails the refusal traps; the scorer must
    # notice rather than pass everything.
    assert traps["metrics"]["trap_pass_rate"] < 1


def test_every_eval_review_loads():
    for name in ("fixture", "breach-pattern", "medicare-platform"):
        review = chat_eval.load_review(name)
        assert review["findings"] and review["workload_brief"]
