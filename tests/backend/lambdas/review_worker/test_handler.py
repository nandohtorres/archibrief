import json
from types import SimpleNamespace

import boto3
import pytest

from backend.lambdas.clarify_review import handler as clarify
from backend.lambdas.finalize.handler import handler as finalize
from backend.lambdas.review_worker import handler as worker
from backend.lambdas.store_clarification_token.handler import handler as store_token
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
    monkeypatch.setattr(clarify, "paid_work_allowed", lambda: True)
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


def test_clarification_history_contains_only_an_opaque_reference(prepared, monkeypatch):
    review_id, s3, _calls, replies, agent_calls = prepared
    replies.insert(
        0,
        {
            "status": "needs_clarification",
            "needs_clarification": ["budget_ceiling"],
            "preflight_fields": {"budget_ceiling": {"outcome": "paused"}},
        },
    )
    assert worker.handler({"review_id": review_id}, None) == {
        "status": "needs_clarification"
    }
    store_token(
        {
            "review_id": review_id,
            "taskToken": "server-token",
            "reviews_table_name": "reviews",
        },
        None,
    )
    original_client = boto3.client
    callbacks = []
    monkeypatch.setattr(
        boto3,
        "client",
        lambda service, *a, **kw: (
            SimpleNamespace(
                send_task_success=lambda **payload: callbacks.append(payload)
            )
            if service == "stepfunctions"
            else original_client(service, *a, **kw)
        ),
    )
    event = {
        "pathParameters": {"reviewId": review_id},
        "headers": dict(visitor.HEADERS),
        "requestContext": visitor.REQUEST_CONTEXT,
        "body": json.dumps(
            {
                "answers": {"budget_ceiling": "50000"},
                "additional_notes": "Private customer workload",
            }
        ),
    }
    assert clarify.handler(event, None)["statusCode"] == 200
    callback = json.loads(callbacks[0]["output"])
    assert set(callback) == {"resume_key"}
    assert "Private customer" not in callbacks[0]["output"]
    stored = json.loads(
        s3.get_object(Bucket="reports", Key=callback["resume_key"])["Body"].read()
    )
    assert stored["answers"] == {"budget_ceiling": "50000"}
    assert worker.handler(
        {"review_id": review_id, "phase": "resume", **callback}, None
    ) == {"status": "complete"}
    assert len(agent_calls) == 2
    assert "Private customer workload" in agent_calls[-1]["payload"]["workload_brief"]


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


def test_malformed_resume_key_fails_without_releasing_anything(prepared):
    review_id, *_ = prepared
    event = {"review_id": review_id, "phase": "resume", "resume_key": "jobs/other.json"}
    assert worker.handler(event, None) == {"status": "failed"}
    counters = boto3.resource("dynamodb").Table("counters").scan()["Items"]
    assert not any(row.get("released") for row in counters)


def test_agent_service_error_logs_stage_and_code_without_content(
    prepared, monkeypatch, capsys
):
    from botocore.exceptions import ClientError

    review_id, *_ = prepared

    def invoke(**kwargs):
        raise ClientError(
            {
                "Error": {
                    "Code": "RuntimeClientError",
                    "Message": "PRIVATE-CONTENT-CANARY",
                }
            },
            "InvokeAgentRuntime",
        )

    monkeypatch.setattr(
        worker,
        "AgentCoreRuntimeClient",
        lambda **kwargs: SimpleNamespace(invoke=invoke),
    )
    assert worker.handler({"review_id": review_id}, None) == {"status": "failed"}
    out = capsys.readouterr().out
    assert "PRIVATE-CONTENT-CANARY" not in out
    failure = json.loads(
        next(line for line in out.splitlines() if "review_worker_failed" in line)
    )
    assert failure == {
        "event": "review_worker_failed",
        "stage": "reasoning",
        "kind": "ClientError",
        "code": "RuntimeClientError",
    }
