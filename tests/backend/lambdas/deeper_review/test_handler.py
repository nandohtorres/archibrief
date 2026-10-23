"""HTTP admission and durable worker tests. Model fake; AWS storage on moto."""

import json
import time
from types import SimpleNamespace

import boto3
import pytest
from botocore.exceptions import ReadTimeoutError
from moto import mock_aws

from backend.lambdas.deeper_review import handler as api
from backend.lambdas.deeper_review import worker
from backend.lambdas.get_review.handler import handler as get_review
from backend.shared.deeper_jobs import job_id_for, job_key
from tests.backend import visitor

RAW = {
    "finding_id": "child",
    "review_id": "r1",
    "category": "iam",
    "type": "not-observable",
    "finding": "Deeper observation",
    "evidence": "unavailable",
    "citation": None,
    "confidence": 0.7,
    "confidence_inputs": {
        "evidence_directness": 0.7,
        "source_agreement": 0.7,
        "rule_determinism": 0,
    },
    "risk_impact": "unknown",
    "recommendation": "inspect",
    "framework_mapping": [],
    "depth_level": "deep",
    "parent_finding_id": "base",
    "model_id": "test-model",
}
BASE = {
    **RAW,
    "finding_id": "base",
    "depth_level": "lightweight",
    "parent_finding_id": None,
}
LEDGER = {
    "workload_brief": "PRIVATE WORKLOAD",
    "findings": [BASE],
    "terraform_resources": {
        "resources": [],
        "not_observable": ["remote module omitted"],
    },
    "baseline_answers": [
        {"field": "availability_criticality", "value": "99.9%", "outcome": "assumption"}
    ],
}


def event(rid="r1", fid="base"):
    return {
        "headers": dict(visitor.HEADERS),
        "requestContext": visitor.REQUEST_CONTEXT,
        "pathParameters": {"reviewId": rid, "findingId": fid},
    }


@pytest.fixture
def env(monkeypatch):
    with mock_aws():
        monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
        visitor.enable_public(monkeypatch)
        for key, value in {
            "REVIEWS_TABLE_NAME": "reviews",
            "FINDINGS_TABLE_NAME": "findings",
            "REPORTS_BUCKET_NAME": "reports",
            "USAGE_COUNTERS_TABLE_NAME": "counters",
            "AGENTCORE_RUNTIME_ARN": "test-runtime",
        }.items():
            monkeypatch.setenv(key, value)
        db = boto3.resource("dynamodb", region_name="us-east-1")
        tables = {}
        for name, keys in [
            ("reviews", ["reviewId"]),
            ("findings", ["reviewId", "findingId"]),
            ("counters", ["counterKey"]),
        ]:
            tables[name] = db.create_table(
                TableName=name,
                KeySchema=[
                    {"AttributeName": k, "KeyType": "HASH" if i == 0 else "RANGE"}
                    for i, k in enumerate(keys)
                ],
                AttributeDefinitions=[
                    {"AttributeName": k, "AttributeType": "S"} for k in keys
                ],
                BillingMode="PAY_PER_REQUEST",
            )
        tables["reviews"].put_item(
            Item={
                "reviewId": "r1",
                "status": "complete",
                "ttl": int(time.time()) + 86400,
                "reportS3Key": "reports/r1/evidence-ledger.json",
                **visitor.review_fields(),
            }
        )
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="reports")
        s3.put_object(
            Bucket="reports",
            Key="reports/r1/evidence-ledger.json",
            Body=json.dumps(LEDGER).encode(),
        )
        sfn = boto3.client("stepfunctions", region_name="us-east-1")
        arn = sfn.create_state_machine(
            name="deeper",
            roleArn="arn:aws:iam::000000000000:role/workflow",
            definition=json.dumps(
                {"StartAt": "Done", "States": {"Done": {"Type": "Succeed"}}}
            ),
        )["stateMachineArn"]
        monkeypatch.setenv("DEEPER_STATE_MACHINE_ARN", arn)
        state = SimpleNamespace(
            tables=tables,
            s3=s3,
            sfn=sfn,
            arn=arn,
            calls=[],
            response={
                "findings": [RAW],
                "model_output_counts": {"attempted": 2, "accepted": 1, "rejected": 1},
            },
            error=None,
            on_invoke=None,
        )

        def invoke(**kwargs):
            state.calls.append(kwargs)
            if state.on_invoke:
                state.on_invoke()
            if state.error:
                raise state.error
            return state.response

        def client(**kwargs):
            state.client_options = kwargs
            return SimpleNamespace(invoke=invoke)

        monkeypatch.setattr(worker, "AgentCoreRuntimeClient", client)
        monkeypatch.setattr(worker, "paid_work_allowed", lambda: True)
        monkeypatch.setattr(api, "paid_work_allowed", lambda: True)
        yield state


def run(phase="run"):
    return worker.run_job(
        {
            "review_id": "r1",
            "finding_id": "base",
            "job_id": job_id_for("r1", "base"),
            "phase": phase,
        },
        None,
    )


def job(env):
    return env.tables["findings"].get_item(
        Key=job_key("r1", "base"), ConsistentRead=True
    )["Item"]


def test_http_returns_202_without_calling_the_model_and_dispatches_only_ids(env):
    result = api.handler(event(), None)
    assert result["statusCode"] == 202
    assert env.calls == []
    assert job(env)["status"] == "pending"
    execution = env.sfn.list_executions(stateMachineArn=env.arn)["executions"][0]
    payload = json.loads(
        env.sfn.describe_execution(executionArn=execution["executionArn"])["input"]
    )
    assert payload == {
        "review_id": "r1",
        "finding_id": "base",
        "job_id": job_id_for("r1", "base"),
    }
    assert "PRIVATE" not in json.dumps(payload)


def test_repeated_admission_reuses_execution_and_reservation(env):
    assert api.handler(event(), None)["statusCode"] == 202
    first = env.tables["counters"].scan()["Items"]
    assert api.handler(event(), None)["statusCode"] == 202
    assert len(env.sfn.list_executions(stateMachineArn=env.arn)["executions"]) == 1
    assert env.tables["counters"].scan()["Items"] == first
    assert env.calls == []


def test_ambiguous_dispatch_is_recovered_with_the_same_execution_and_reservation(
    env, monkeypatch
):
    original = boto3.client
    actual = env.sfn

    def ambiguous(**kwargs):
        actual.start_execution(**kwargs)
        raise ReadTimeoutError(endpoint_url="stepfunctions")

    monkeypatch.setattr(
        api.boto3,
        "client",
        lambda service, **kwargs: (
            SimpleNamespace(start_execution=ambiguous)
            if service == "stepfunctions"
            else original(service, **kwargs)
        ),
    )
    assert api.handler(event(), None)["statusCode"] == 503
    reserved = env.tables["counters"].scan()["Items"]
    monkeypatch.setattr(api.boto3, "client", original)
    assert api.handler(event(), None)["statusCode"] == 202
    assert len(env.sfn.list_executions(stateMachineArn=env.arn)["executions"]) == 1
    assert env.tables["counters"].scan()["Items"] == reserved
    assert env.calls == []


def test_invalid_write_capability_does_not_reserve_or_dispatch(env):
    request = event()
    request["headers"]["x-review-write-token"] = "x" * 43
    assert api.handler(request, None)["statusCode"] == 404
    assert env.tables["counters"].scan()["Items"] == []


def test_worker_persists_result_and_quality_once_and_report_reload_keeps_it(env):
    api.handler(event(), None)
    assert run() == {"status": "complete"}
    assert run() == {"status": "complete"}
    assert len(env.calls) == 1
    assert env.client_options["read_timeout_seconds"] == 300
    first = api.handler(event(), None)
    assert first["statusCode"] == 200
    assert json.loads(first["body"])["analysis_quality"]["outcome"] == "partial"
    assert api.handler(event(), None) == first
    report = json.loads(get_review(event(), None)["body"])
    assert {f["record"]["finding_id"] for f in report["findings"]} == {"base", "child"}
    assert report["deeper_jobs"][0]["status"] == "complete"
    assert report["report_projection"]["excluded_child_count"] == 0
    assert (
        json.loads(
            env.s3.get_object(Bucket="reports", Key="reports/r1/evidence-ledger.json")[
                "Body"
            ].read()
        )
        == LEDGER
    )


def test_context_and_assumptions_reach_the_background_model(env):
    api.handler(event(), None)
    run()
    payload = env.calls[0]["payload"]
    assert payload["parent_finding"] == BASE
    assert payload["terraform_resources"] == LEDGER["terraform_resources"]
    assert (
        payload["preflight_fields"]["availability_criticality"]["is_assumption"] is True
    )


def test_duplicate_delivery_while_running_never_calls_the_model_twice(env):
    api.handler(event(), None)
    observed = []
    env.on_invoke = lambda: observed.append(run())
    assert run() == {"status": "complete"}
    assert observed == [{"status": "in_progress"}]
    assert len(env.calls) == 1


def test_model_timeout_is_terminal_and_does_not_autoretry(env):
    api.handler(event(), None)
    env.error = ReadTimeoutError(endpoint_url="PRIVATE-CANARY")
    assert run() == {"status": "failed"}
    assert run() == {"status": "failed"}
    assert api.handler(event(), None)["statusCode"] == 409
    assert len(env.calls) == 1
    assert job(env)["failure_code"] == "analysis_failed"


def test_worker_exception_does_not_leak_private_error_text(env, capsys):
    api.handler(event(), None)
    env.error = RuntimeError("PRIVATE-CANARY")
    assert run() == {"status": "failed"}
    assert "PRIVATE-CANARY" not in capsys.readouterr().out


def test_workflow_timeout_cleanup_cannot_be_overwritten_by_a_late_result(env):
    api.handler(event(), None)
    env.on_invoke = lambda: run("fail")
    assert run() == {"status": "failed"}
    assert job(env)["status"] == "failed"
    assert all(
        item.get("kind") == "deeper-job"
        for item in env.tables["findings"].scan()["Items"]
    )


def test_cleanup_cannot_overwrite_a_committed_result(env):
    api.handler(event(), None)
    run()
    run("fail")
    assert job(env)["status"] == "complete"


def test_all_rejected_output_is_retained_for_replay_without_spend(env):
    api.handler(event(), None)
    env.response = {
        "findings": [],
        "model_output_counts": {"attempted": 2, "accepted": 0, "rejected": 2},
    }
    assert run() == {"status": "complete"}
    first = api.handler(event(), None)
    assert first["statusCode"] == 502
    assert json.loads(first["body"])["analysis_quality"]["outcome"] == "all-rejected"
    assert api.handler(event(), None) == first
    assert len(env.calls) == 1


def test_no_findings_is_distinct_from_all_rejected(env):
    api.handler(event(), None)
    env.response = {
        "findings": [],
        "model_output_counts": {"attempted": 0, "accepted": 0, "rejected": 0},
    }
    run()
    assert api.handler(event(), None)["statusCode"] == 200


@pytest.mark.parametrize(
    "rid,fid,status",
    [
        (None, "base", 400),
        ("r1", None, 400),
        ("unknown", "base", 404),
        ("r1", "unknown", 404),
        ("r1", "child", 404),
    ],
)
def test_invalid_scope_never_dispatches(env, rid, fid, status):
    assert api.handler(event(rid, fid), None)["statusCode"] == status
    assert env.sfn.list_executions(stateMachineArn=env.arn)["executions"] == []


def test_paused_admission_does_not_reserve_or_dispatch(env, monkeypatch):
    monkeypatch.setattr(api, "paid_work_allowed", lambda: False)
    assert api.handler(event(), None)["statusCode"] == 503
    assert env.tables["counters"].scan()["Items"] == []


def test_worker_rechecks_pause_before_paid_call(env, monkeypatch):
    api.handler(event(), None)
    monkeypatch.setattr(worker, "paid_work_allowed", lambda: False)
    assert run() == {"status": "failed"}
    assert env.calls == []


def test_completed_replay_is_available_while_paid_work_is_paused(env, monkeypatch):
    api.handler(event(), None)
    run()
    monkeypatch.setattr(api, "paid_work_allowed", lambda: False)
    assert api.handler(event(), None)["statusCode"] == 200


def test_expired_job_does_not_start_again_and_expiry_does_not_renew(env):
    api.handler(event(), None)
    original_ttl = job(env)["ttl"]
    env.tables["findings"].update_item(
        Key=job_key("r1", "base"),
        UpdateExpression="SET deadline = :past",
        ExpressionAttributeValues={":past": 1},
    )
    assert api.handler(event(), None)["statusCode"] == 409
    assert run() == {"status": "failed"}
    assert env.calls == []
    assert job(env)["ttl"] == original_ttl


def test_worker_rejects_content_bearing_or_forged_envelopes(env):
    with pytest.raises(ValueError, match="envelope"):
        worker.run_job({"review_id": "r1", "workload_brief": "PRIVATE"}, None)
    with pytest.raises(ValueError, match="identity"):
        worker.run_job(
            {
                "review_id": "r1",
                "finding_id": "base",
                "job_id": "forged",
                "phase": "run",
            },
            None,
        )
