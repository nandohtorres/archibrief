import json
from types import SimpleNamespace

import pytest
from botocore.exceptions import ReadTimeoutError
from botocore.stub import Stubber

from backend.shared.clients import BedrockReasoningClient, ModelOutputTruncated
from backend.shared.evaluation_budget import EvaluationBudget, EvaluationLimitReached


def budget(tmp_path, clock=lambda: 0, **overrides):
    plan = {
        "max_paid_calls": 2,
        "max_seconds": 10,
        "max_request_bytes": 2000,
        "max_model_output_tokens_per_call": 1000,
        "monetary_limit_enforced": False,
        **overrides,
    }
    return EvaluationBudget(plan, tmp_path / "calls.json", clock=clock)


def test_call_limit_is_checked_before_dispatch_and_failed_calls_stay_counted(tmp_path):
    run = budget(tmp_path, max_paid_calls=1)
    calls = []

    def fail(text):
        calls.append(text)
        assert json.loads(run.path.read_text())["calls"][0]["outcome"] == "started"
        raise ReadTimeoutError(endpoint_url="PRIVATE-CANARY")

    client = run.wrap(SimpleNamespace(embed=fail), "embedding")
    with pytest.raises(ReadTimeoutError):
        client.embed("PRIVATE-QUERY")
    with pytest.raises(EvaluationLimitReached, match="call_limit"):
        client.embed("second")
    assert len(calls) == 1
    evidence = run.path.read_text()
    assert "PRIVATE" not in evidence
    assert json.loads(evidence)["calls"][0]["outcome"] == "failed"
    assert json.loads(evidence)["calls"][0]["usage"] is None


@pytest.mark.parametrize("kind", ["deadline", "request", "output"])
def test_limits_prevent_the_next_call_without_dispatch(kind, tmp_path):
    tick = [0]
    run = budget(tmp_path, clock=lambda: tick[0])
    calls = []
    client = run.wrap(
        SimpleNamespace(converse_structured=lambda **kw: calls.append(kw)), "reasoning"
    )
    kwargs = {"user_content": "small", "max_tokens": 100}
    if kind == "deadline":
        tick[0] = 11
    elif kind == "request":
        kwargs["user_content"] = "x" * 3000
    else:
        kwargs["max_tokens"] = 1001
    with pytest.raises(EvaluationLimitReached):
        client.converse_structured(**kwargs)
    assert calls == [] and run.summary()["dispatched_calls"] == 0


def test_unbudgeted_methods_cannot_bypass_the_meter(tmp_path):
    run = budget(tmp_path)
    calls = []
    client = run.wrap(
        SimpleNamespace(list_vectors=lambda: calls.append(True)), "vectors"
    )
    with pytest.raises(EvaluationLimitReached, match="unbudgeted_operation"):
        client.list_vectors()
    assert calls == []


def test_failed_generation_keeps_its_aggregate_token_reservation(tmp_path):
    run = budget(tmp_path, max_generated_tokens=150)
    calls = []

    def fail(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("PRIVATE-FAILURE-CANARY")

    client = run.wrap(SimpleNamespace(converse_structured=fail), "reasoning")
    with pytest.raises(RuntimeError):
        client.converse_structured(user_content="PRIVATE-PROMPT", max_tokens=100)
    with pytest.raises(EvaluationLimitReached, match="generated_token_limit"):
        client.converse_structured(user_content="second", max_tokens=100)
    assert len(calls) == 1
    assert run.summary()["reserved_output_tokens"] == 100
    assert "PRIVATE" not in run.path.read_text()


def test_known_usage_is_allowlisted_and_never_includes_model_text(tmp_path):
    run = budget(tmp_path)
    client = run.wrap(
        SimpleNamespace(
            converse_tool_cached=lambda **kw: (
                {"answer": "PRIVATE"},
                {"inputTokens": 12, "outputTokens": 4, "secret": "PRIVATE"},
            )
        ),
        "reasoning",
    )
    client.converse_tool_cached(max_tokens=100)
    assert run.summary()["calls"][0]["usage"] == {"inputTokens": 12, "outputTokens": 4}
    assert "PRIVATE" not in run.path.read_text()


def test_sdk_usage_survives_structured_output_rejection(tmp_path):
    run = budget(tmp_path)
    client = BedrockReasoningClient(model_id="test", no_retries=True)
    stubber = Stubber(client._client)
    stubber.add_response(
        "converse",
        {
            "output": {
                "message": {"role": "assistant", "content": [{"text": "PRIVATE"}]}
            },
            "stopReason": "max_tokens",
            "usage": {"inputTokens": 12, "outputTokens": 4, "totalTokens": 16},
            "metrics": {"latencyMs": 10},
        },
    )
    with stubber, pytest.raises(ModelOutputTruncated):
        run.wrap(client, "reasoning").converse_structured(
            system_prompt="system",
            user_content="PRIVATE",
            max_tokens=100,
            tool_name="emit",
            tool_description="emit",
            input_schema={"type": "object"},
        )
    assert run.summary()["calls"][0]["usage"] == {"inputTokens": 12, "outputTokens": 4}
    assert run.summary()["calls"][0]["outcome"] == "failed"
    assert "PRIVATE" not in run.path.read_text()


def test_existing_journal_is_never_overwritten(tmp_path):
    original = budget(tmp_path)
    before = original.path.read_text()
    with pytest.raises(FileExistsError):
        budget(tmp_path)
    assert original.path.read_text() == before
