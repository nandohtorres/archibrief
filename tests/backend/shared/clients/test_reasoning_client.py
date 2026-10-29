import json

import pytest

from backend.shared.clients import (
    BedrockReasoningClient,
    ModelOutputTruncated,
    ReasoningDeadlineExceeded,
    ToolCallMissing,
)


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


class _Stream:
    def __init__(self, events, clock=None):
        self.events = events
        self.clock = clock
        self.closed = False

    def __iter__(self):
        for event in self.events:
            if self.clock is not None:
                self.clock[0] += 100
            yield event

    def close(self):
        self.closed = True


class _ConverseStream:
    def __init__(self, stream):
        self.stream = stream
        self.request = None

    def converse_stream(self, **kwargs):
        self.request = kwargs
        return {"stream": self.stream}


def _streaming_client(stream, deadline=420.0) -> BedrockReasoningClient:
    client = BedrockReasoningClient(
        model_id="m", region_name="us-east-1", stream_deadline_seconds=deadline
    )
    client._client = _ConverseStream(stream)
    return client


def _tool_events(fragments, stop_reason="tool_use"):
    return [
        {"messageStart": {"role": "assistant"}},
        {
            "contentBlockStart": {
                "contentBlockIndex": 0,
                "start": {"toolUse": {"toolUseId": "t1", "name": "emit_findings"}},
            }
        },
        *[
            {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"toolUse": {"input": part}}}}
            for part in fragments
        ],
        {"contentBlockStop": {"contentBlockIndex": 0}},
        {"messageStop": {"stopReason": stop_reason}},
        {
            "metadata": {
                "usage": {"inputTokens": 30000, "outputTokens": 6100},
                "metrics": {"latencyMs": 250000},
            }
        },
    ]


def test_streamed_call_reassembles_the_tool_input(capsys):
    stream = _Stream(_tool_events(['{"findings": [{"fin', 'ding": "x"}]}']))
    client = _streaming_client(stream)
    assert _call(client) == {"findings": [{"finding": "x"}]}
    assert stream.closed
    assert client._client.request["toolConfig"]["toolChoice"] == {
        "tool": {"name": "emit_findings"}
    }
    assert _logged(capsys) == {
        "event": "reasoning_call",
        "stop_reason": "tool_use",
        "input_tokens": 30000,
        "output_tokens": 6100,
        "max_tokens": 8192,
        "latency_ms": 250000,
    }


def test_streamed_truncation_never_parses_the_partial_answer(capsys):
    stream = _Stream(_tool_events(['{"findings": [{"fin'], stop_reason="max_tokens"))
    with pytest.raises(ModelOutputTruncated):
        _call(_streaming_client(stream))
    assert _logged(capsys)["output_tokens"] == 6100


def test_streamed_call_past_its_deadline_stops_and_closes_the_stream(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("backend.shared.clients.time.monotonic", lambda: clock[0])
    stream = _Stream(_tool_events(['{"findings": []}']), clock=clock)
    with pytest.raises(ReasoningDeadlineExceeded):
        _call(_streaming_client(stream, deadline=250.0))
    assert stream.closed


def test_streamed_tool_input_that_is_not_json_is_a_missing_tool_call():
    stream = _Stream(_tool_events(['{"findings": [']))
    with pytest.raises(ToolCallMissing):
        _call(_streaming_client(stream))
