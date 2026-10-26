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


def test_failed_attempts_stay_in_quality_and_trap_denominators(monkeypatch):
    def fail(*args):
        raise RuntimeError("PRIVATE-CANARY")

    monkeypatch.setattr(chat_eval, "_ask", fail)
    quality = chat_eval.run_quality(None, "canary", None)
    traps = chat_eval.run_traps(None, "canary", None)
    assert len(quality["rows"]) == 24
    assert quality["metrics"]["attempt_completion_rate"] == 0
    assert quality["metrics"]["mean_cost_usd"] is None
    assert quality["metrics"]["measured_cost_attempts"] == 0
    assert traps["metrics"]["trap_pass_rate"] == 0
    assert all(row["failures"] == ["execution_failed"] for row in traps["rows"])
    assert "quality_completion: incomplete" in chat_eval.failed_pass_bars(
        {"quality": quality, "traps": traps}
    )
    assert "PRIVATE-CANARY" not in str(quality)


def test_declared_pass_bars_fail_missing_and_bad_metrics():
    quality = {
        "status_accuracy": 1,
        "citation_recall": 1,
        "citation_integrity": 1,
        "refusal_correctness": 1,
        "false_refusal": 0,
    }
    results = {
        "quality": {"metrics": quality},
        "traps": {"metrics": {"trap_pass_rate": 1}},
    }
    assert chat_eval.failed_pass_bars(results) == []
    quality["citation_integrity"] = None
    quality["false_refusal"] = 0.2
    results["traps"]["metrics"]["trap_pass_rate"] = 0
    assert set(chat_eval.failed_pass_bars(results)) == {
        "citation_integrity: not measured",
        "false_refusal_max: threshold not met",
        "trap_pass_rate: threshold not met",
    }


def test_failed_quality_gates_return_nonzero_after_writing_evidence(
    monkeypatch, tmp_path
):
    import json

    output = tmp_path / "eval.json"
    for client in (
        "BedrockReasoningClient",
        "BedrockEmbeddingClient",
        "S3VectorsClient",
    ):
        monkeypatch.setattr(chat_eval, client, lambda **kwargs: None)
    monkeypatch.setattr(
        chat_eval,
        "run_quality",
        lambda *args: {"metrics": {"status_accuracy": 0}, "rows": []},
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "eval",
            "--confirm-paid",
            "--max-paid-calls",
            "100",
            "--run-log",
            str(tmp_path / "calls.json"),
            "--out",
            str(output),
        ],
    )
    assert chat_eval.main() == 1
    evidence = json.loads(output.read_text())
    assert evidence["gate_failures"]
    assert evidence["not_evaluated_gates"] == ["trap_pass_rate"]
