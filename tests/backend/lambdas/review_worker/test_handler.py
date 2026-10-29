import json
import os
from types import SimpleNamespace

import boto3
import pytest

from backend.lambdas.finalize.handler import handler as finalize
from backend.lambdas.review_worker import handler as worker
from tests.backend import visitor
from tests.backend.lambdas.submit_review.test_handler import (  # noqa: F401 - shared moto fixture
    _submit,
    env,
)


@pytest.fixture
def prepared(env, monkeypatch):  # noqa: F811 - pytest consumes the imported fixture
    upload, body, s3, _sfn, _arn = env
    assert _submit(body)["statusCode"] == 202
    monkeypatch.setattr(worker, "paid_work_allowed", lambda: True)
    monkeypatch.setenv("AGENTCORE_RUNTIME_ARN", "test-runtime")
    calls = []
    replies = [{"status": "complete", "findings": [], "preflight_fields": {}}]

    def stage(name, payload):
        calls.append((name, payload))
        return {
            "ingest": lambda: {
                "status": "parsed",
                "parsed_s3_key": "parsed/x.json",
                "resource_count": 1,
            },
            "scan": lambda: {"status": "unavailable"},
            "rule_engine": lambda: {
                "findings": [],
                "rule_version": "test",
                "resource_summary": {},
            },
            "validate": lambda: {"valid_findings": []},
            "audit": lambda: {"status": "recorded"},
            "finalize": lambda: finalize(payload, None),
        }[name]()

    monkeypatch.setattr(worker, "_invoke", stage)
    agent_calls = []

    def invoke(**kwargs):
        agent_calls.append(kwargs)
        return replies.pop(0)

    monkeypatch.setattr(
        worker,
        "AgentCoreRuntimeClient",
        lambda **kwargs: SimpleNamespace(invoke=invoke),
    )
    return upload["reviewId"], s3, calls, replies, agent_calls


def test_completed_worker_returns_only_status_and_uses_bound_archive_version(prepared):
    review_id, _s3, calls, _replies, agent_calls = prepared
    result = worker.handler({"review_id": review_id, "phase": "initial"}, None)
    assert result == {"status": "complete"}
    assert calls[0][1]["archive_s3_version"]
    assert worker.handler({"review_id": review_id, "phase": "initial"}, None) == result
    assert len(agent_calls) == 1


def test_rejected_output_remains_visible_after_worker_finalize_and_report_read(
    prepared, monkeypatch
):
    from backend.chat.context import build_review_context
    from backend.lambdas.validate.handler import handler as validate
    from backend.shared.report import build_review_report

    review_id, s3, _calls, replies, _agent_calls = prepared
    replies[0].update(
        findings=[{"private": "REJECTED-CONTENT-CANARY"}],
        model_output_counts={"attempted": 3, "accepted": 1, "rejected": 2},
    )
    original = worker._invoke
    monkeypatch.setattr(
        worker,
        "_invoke",
        lambda name, payload: (
            validate(payload, None) if name == "validate" else original(name, payload)
        ),
    )
    assert worker.handler({"review_id": review_id}, None) == {"status": "complete"}
    ledger = json.loads(
        s3.get_object(
            Bucket="reports", Key=f"reports/{review_id}/evidence-ledger.json"
        )["Body"].read()
    )
    report = build_review_report({"reviewId": review_id}, ledger)
    quality = report["analysis_quality"]
    assert quality["outcome"] == "all-rejected"
    assert quality["model_verification"]["rejected"] == 2
    assert quality["schema_validation"]["rejected"] == 1
    assert build_review_context(ledger).review_data["analysis_quality"] == quality
    assert "REJECTED-CONTENT-CANARY" not in json.dumps(report)


def test_a_preflight_pause_fails_instead_of_waiting(prepared):
    # No field pauses any more; if preflight ever asks, the review fails
    # rather than waiting on a question nobody can answer.
    review_id, _s3, _calls, replies, _agent_calls = prepared
    replies.insert(
        0,
        {
            "status": "needs_clarification",
            "needs_clarification": ["budget_ceiling"],
            "preflight_fields": {"budget_ceiling": {"outcome": "paused"}},
        },
    )
    assert worker.handler({"review_id": review_id}, None) == {"status": "failed"}
    review = boto3.resource("dynamodb").Table("reviews").get_item(
        Key={"reviewId": review_id}
    )["Item"]
    assert review["failureCode"] == "internal_error"


def test_payload_bearing_envelope_is_rejected_before_work(prepared):
    review_id, _s3, calls, _replies, _agent_calls = prepared
    with pytest.raises(ValueError, match="workflow envelope"):
        worker.handler(
            {"review_id": review_id, "workload_brief": "must not enter history"}, None
        )
    assert calls == []


def test_stage_exception_never_leaks_content_to_history_or_logs(
    prepared, monkeypatch, capsys
):
    review_id, *_ = prepared

    def fail(*args):
        raise RuntimeError("PRIVATE-CONTENT-CANARY")

    monkeypatch.setattr(worker, "_invoke", fail)
    assert worker.handler({"review_id": review_id}, None) == {"status": "failed"}
    assert "PRIVATE-CONTENT-CANARY" not in capsys.readouterr().out


def test_rejected_archive_fails_and_releases_the_reservation(prepared, monkeypatch):
    review_id, _s3, _calls, _replies, agent_calls = prepared
    monkeypatch.setattr(worker, "_invoke", lambda name, payload: {"status": "rejected"})
    assert worker.handler({"review_id": review_id}, None) == {"status": "failed"}
    assert agent_calls == []
    counters = boto3.resource("dynamodb").Table("counters").scan()["Items"]
    claim = next(row for row in counters if row["counterKey"].endswith("#initial"))
    assert claim["released"] is True
    assert all(
        row["spent"] == 0 for row in counters if row["counterKey"].startswith("paid#")
    )


def test_failure_after_the_model_call_keeps_the_reservation(prepared, monkeypatch):
    review_id, *_ = prepared
    original = worker._invoke

    def fail_validate(name, payload):
        if name == "validate":
            raise RuntimeError("boom")
        return original(name, payload)

    monkeypatch.setattr(worker, "_invoke", fail_validate)
    assert worker.handler({"review_id": review_id}, None) == {"status": "failed"}
    counters = boto3.resource("dynamodb").Table("counters").scan()["Items"]
    assert not any(row.get("released") for row in counters)


def test_blocked_input_keeps_the_reservation(prepared, monkeypatch):
    # Guardrails, which is billed, has already run when ingest blocks input.
    review_id, *_ = prepared
    monkeypatch.setattr(worker, "_invoke", lambda name, payload: {"status": "blocked"})
    assert worker.handler({"review_id": review_id}, None) == {"status": "failed"}
    counters = boto3.resource("dynamodb").Table("counters").scan()["Items"]
    assert not any(row.get("released") for row in counters)


def test_resume_phase_is_rejected(prepared):
    review_id, _s3, calls, _replies, _agent_calls = prepared
    with pytest.raises(ValueError, match="workflow phase"):
        worker.handler({"review_id": review_id, "phase": "resume"}, None)
    with pytest.raises(ValueError, match="workflow envelope"):
        worker.handler(
            {"review_id": review_id, "phase": "resume", "resume_key": "jobs/x.json"}, None
        )
    assert calls == []


def test_a_model_failure_still_publishes_the_rule_findings(prepared, monkeypatch, capsys):
    from botocore.exceptions import ClientError

    from backend.shared.report import build_review_report

    review_id, s3, calls, _replies, _agent_calls = prepared
    rule_finding = {"rule": "RULE-FINDING"}
    original = worker._invoke

    def stage(name, payload):
        if name == "rule_engine":
            calls.append((name, payload))
            return {"findings": [rule_finding], "rule_version": "test", "resource_summary": {}}
        return original(name, payload)

    def invoke(**kwargs):
        raise ClientError(
            {"Error": {"Code": "RuntimeClientError", "Message": "PRIVATE-CONTENT-CANARY"}},
            "InvokeAgentRuntime",
        )

    monkeypatch.setattr(worker, "_invoke", stage)
    monkeypatch.setattr(
        worker,
        "AgentCoreRuntimeClient",
        lambda **kwargs: SimpleNamespace(invoke=invoke),
    )
    assert worker.handler({"review_id": review_id}, None) == {"status": "complete"}
    out = capsys.readouterr().out
    assert "PRIVATE-CONTENT-CANARY" not in out
    logged = json.loads(next(line for line in out.splitlines() if "reasoning_unavailable" in line))
    assert logged == {"event": "reasoning_unavailable", "kind": "ClientError"}
    assert dict(calls)["validate"] == {"findings": [rule_finding]}
    ledger = json.loads(
        s3.get_object(
            Bucket="reports", Key=f"reports/{review_id}/evidence-ledger.json"
        )["Body"].read()
    )
    quality = build_review_report({"reviewId": review_id}, ledger)["analysis_quality"]
    assert "model_unavailable" in quality["reason_codes"]
    assert quality["model_verification"] == {"attempted": 0, "accepted": 0, "rejected": 0}


def test_agent_wait_fits_the_time_the_lambda_has_left():
    def context(seconds_left):
        return SimpleNamespace(get_remaining_time_in_millis=lambda: seconds_left * 1000)

    assert worker._agent_read_timeout(None) == worker.AGENT_READ_TIMEOUT_SECONDS
    assert worker._agent_read_timeout(context(880)) == worker.AGENT_READ_TIMEOUT_SECONDS
    assert worker._agent_read_timeout(context(500)) == 500 - worker.POST_AGENT_RESERVE_SECONDS
    assert worker._agent_read_timeout(context(100)) == 60


GRAPH = {
    "version": 1,
    "lanes": ["data"],
    "nodes": [
        {
            "id": "aws_s3_bucket.logs",
            "type": "aws_s3_bucket",
            "name": "logs",
            "label": "S3 bucket",
            "lane": "data",
            "details": [],
            "findings": [],
        }
    ],
    "edges": [],
    "account_findings": [],
    "truncated": False,
}


def test_diagram_is_saved_for_the_progress_screen_before_the_model_runs(
    prepared, monkeypatch
):
    review_id, s3, _calls, _replies, agent_calls = prepared
    original = worker._invoke
    seen_before_model = []

    def stage(name, payload):
        result = original(name, payload)
        return {**result, "architecture": GRAPH} if name == "rule_engine" else result

    def invoke(**kwargs):
        seen_before_model.append(
            s3.get_object(Bucket="reports", Key=f"jobs/{review_id}/architecture.json")
        )
        return {"status": "complete", "findings": [], "preflight_fields": {}}

    monkeypatch.setattr(worker, "_invoke", stage)
    monkeypatch.setattr(
        worker,
        "AgentCoreRuntimeClient",
        lambda **kwargs: SimpleNamespace(invoke=invoke),
    )
    assert worker.handler({"review_id": review_id}, None) == {"status": "complete"}
    assert len(seen_before_model) == 1
    saved = json.loads(seen_before_model[0]["Body"].read())
    assert [node["id"] for node in saved["nodes"]] == ["aws_s3_bucket.logs"]
    assert saved["nodes"][0]["findings"] == []
    item = (
        boto3.resource("dynamodb")
        .Table(os.environ["REVIEWS_TABLE_NAME"])
        .get_item(Key={"reviewId": review_id})["Item"]
    )
    assert item["previewArchitectureKey"] == f"jobs/{review_id}/architecture.json"


def test_a_failed_diagram_preview_does_not_fail_the_review(
    prepared, monkeypatch, capsys
):
    review_id, *_ = prepared
    original = worker._invoke
    monkeypatch.setattr(
        worker,
        "_invoke",
        lambda name, payload: (
            {**original(name, payload), "architecture": {"nodes": "not-a-graph"}}
            if name == "rule_engine"
            else original(name, payload)
        ),
    )
    assert worker.handler({"review_id": review_id}, None) == {"status": "complete"}
    assert "preview_diagram_failed" in capsys.readouterr().out
