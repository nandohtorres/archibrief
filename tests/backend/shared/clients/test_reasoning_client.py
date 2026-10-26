import json

import pytest

from backend.shared.clients import BedrockReasoningClient, ModelOutputTruncated


class _Converse:
    def __init__(self, response):
        self.response = response

    def converse(self, **_kwargs):
        return self.response


def _client(response) -> BedrockReasoningClient:
    client = BedrockReasoningClient(model_id="m", region_name="us-east-1")
    client._client = _Converse(response)
    return client


def _call(client):
    return client.converse_structured(
        system_prompt="PRIVATE-PROMPT",
        user_content="PRIVATE-CONTENT",
        max_tokens=8192,
        tool_name="emit_findings",
        tool_description="d",
        input_schema={"type": "object"},
    )


def _logged(capsys) -> dict:
    out = capsys.readouterr().out
    assert "PRIVATE" not in out
    return json.loads(
        next(line for line in out.splitlines() if "reasoning_call" in line)
    )


def test_structured_call_logs_sizes_and_timing_only(capsys):
    response = {
        "stopReason": "tool_use",
        "usage": {"inputTokens": 1200, "outputTokens": 5400},
        "metrics": {"latencyMs": 71000},
        "output": {
            "message": {
                "content": [
                    {"toolUse": {"name": "emit_findings", "input": {"findings": []}}}
                ]
            }
        },
    }
    assert _call(_client(response)) == {"findings": []}
    assert _logged(capsys) == {
        "event": "reasoning_call",
        "stop_reason": "tool_use",
        "input_tokens": 1200,
        "output_tokens": 5400,
        "max_tokens": 8192,
        "latency_ms": 71000,
    }


def test_truncated_call_is_still_measured(capsys):
    response = {"stopReason": "max_tokens", "usage": {"outputTokens": 8192}}
    with pytest.raises(ModelOutputTruncated):
        _call(_client(response))
    assert _logged(capsys)["output_tokens"] == 8192
