"""scripts/analyze_review_logs.py, on log lines in the runtime's real formats."""

import json

from scripts.analyze_review_logs import overview, render, summarize_stream

STREAM = (
    "2026/11/02/[runtime-logs-archibrief-review-session-"
    "72ff6305-028c-4c84-bb24-204baeed6919-0]46cc1fa8"
)


def _event(timestamp: int, message: object) -> dict:
    return {"timestamp": timestamp, "message": message if isinstance(message, str) else json.dumps(message)}


def _finished_run() -> list[dict]:
    return [
        _event(1, {"event": "reasoning_input", "review_id": "r", "chars": 92000,
                   "resources_sent": 69, "resources_truncated": False, "evidence_passages": 26}),
        _event(2, {"event": "reasoning_call", "stop_reason": "tool_use", "input_tokens": 32447,
                   "output_tokens": 5551, "max_tokens": 12288, "latency_ms": 89644,
                   "elapsed_ms": 89672, "near_max_tokens": False}),
        _event(3, {"event": "reasoning_result", "review_id": "r", "emitted": 12, "capped": 0,
                   "accepted": 11, "rejected": {"quote_not_in_chunk": 1}}),
        _event(4, json.dumps({"level": "INFO", "message": "Invocation completed successfully (93.175s)"})),
    ]


def test_a_finished_review_reports_time_tokens_cost_and_rejections():
    run = summarize_stream(STREAM, _finished_run(), "us.anthropic.claude-sonnet-4-6")
    assert run.review_id == "72ff6305-028c-4c84-bb24-204baeed6919"
    assert run.kind == "review"
    assert run.outcome == "finished"
    assert run.model_seconds == 89.672
    assert run.invocation_seconds == 93.175
    assert (run.input_tokens, run.output_tokens) == (32447, 5551)
    assert run.accepted == 11 and run.rejected == {"quote_not_in_chunk": 1}
    # $3 and $15 per million tokens, plus 10% for the US inference profile.
    assert round(run.cost_usd, 3) == round((32447 * 3 + 5551 * 15) * 1.1 / 1e6, 3)


def test_a_runtime_crash_is_named():
    events = [
        _event(1, "Traceback (most recent call last):"),
        _event(2, "ModuleNotFoundError: No module named 'hcl2'"),
    ]
    run = summarize_stream(STREAM, events, "m")
    assert run.outcome == "runtime crashed"
    assert run.crash == "ModuleNotFoundError: No module named 'hcl2'"


def test_a_timed_out_model_call_is_reported_with_its_wait():
    events = [
        _event(1, {"event": "reasoning_call_failed", "kind": "ReadTimeoutError",
                   "elapsed_ms": 400012, "max_tokens": 12288}),
        _event(2, json.dumps({"message": "Invocation failed (405.1s)"})),
    ]
    run = summarize_stream(STREAM, events, "m")
    assert run.outcome == "model call failed"
    assert run.failure == "ReadTimeoutError"
    assert run.model_seconds == 400.012


def test_streams_that_are_not_reviews_are_skipped():
    assert summarize_stream("2026/11/02/[runtime-logs]otel", _finished_run(), "m") is None


def test_overview_flags_what_needs_attention():
    finished = summarize_stream(STREAM, _finished_run(), "m")
    near = summarize_stream(STREAM.replace("72ff6305", "aaaaaaaa"), _finished_run(), "m")
    near.near_max_tokens = True
    crashed = summarize_stream(
        STREAM.replace("72ff6305", "bbbbbbbb"),
        [_event(1, "ModuleNotFoundError: No module named 'hcl2'")],
        "m",
    )
    totals = overview([finished, near, crashed])
    assert totals["reviews"] == 3 and totals["model_finished"] == 2
    assert totals["findings_rejected_by_kind"] == {"quote_not_in_chunk": 2}
    flagged = {item["review_id"][:8]: item["reasons"] for item in totals["needs_attention"]}
    assert set(flagged) == {"aaaaaaaa", "bbbbbbbb"}
    assert any("max_tokens" in reason for reason in flagged["aaaaaaaa"])
    assert "runtime crashed" in flagged["bbbbbbbb"]
    text = render([finished, near, crashed], totals)
    assert "2 of 3 reviews finished the model step" in text
    assert "Needs attention:" in text
