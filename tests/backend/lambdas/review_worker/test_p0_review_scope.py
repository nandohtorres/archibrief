"""P0 worker outcomes and an unchanged, stubbed AgentCore request boundary."""

import json
from copy import deepcopy
from types import SimpleNamespace

import boto3
import pytest

from backend.lambdas.review_worker import handler as worker
from backend.lambdas.rule_engine.handler import handler as rule_engine
from tests.backend.lambdas.review_worker.test_handler import prepared  # noqa: F401
from tests.backend.lambdas.submit_review.test_handler import env  # noqa: F401
from tests.backend.p0_scope_fixtures import declaration, pending_scope


@pytest.fixture
def scoped_worker(prepared, monkeypatch):  # noqa: F811
    review_id, s3, calls, replies, agent_calls = prepared
    pending = pending_scope([declaration(), declaration(key="capped")])
    # Real, pre-P0 rule-engine output for a one-bucket configuration; a
    # second declared body is deliberately outside this summary fixture.
    rule_result = rule_engine(
        {
            "review_id": review_id,
            "parsed": {"resources": {"aws_s3_bucket": {"main": {}}}},
        },
        None,
    )
    rule_result.update(
        review_scope=pending, summary_members=[["aws_s3_bucket", "main"]]
    )
    original = worker._invoke

    def stage(name, payload):
        if name == "rule_engine":
            calls.append((name, deepcopy(payload)))
            return deepcopy(rule_result)
        return original(name, payload)

    monkeypatch.setattr(worker, "_invoke", stage)
    original_storage = worker.S3Client
    reads = []

    class JobsOnlyStorage:
        def __init__(self, **kwargs):
            self.client = original_storage(**kwargs)

        def get_object(self, key, **kwargs):
            reads.append(key)
            if not key.startswith("jobs/"):
                # pytest.fail escapes the worker's catch-all Exception path.
                pytest.fail(f"worker storage read outside jobs/: {key}")
            return self.client.get_object(key, **kwargs)

        def put_object(self, *args, **kwargs):
            return self.client.put_object(*args, **kwargs)

    monkeypatch.setattr(worker, "S3Client", JobsOnlyStorage)
    return SimpleNamespace(
        review_id=review_id,
        s3=s3,
        calls=calls,
        replies=replies,
        agent_calls=agent_calls,
        rules=rule_result,
        reads=reads,
    )


def _run(case, context=None):
    assert worker.handler({"review_id": case.review_id}, context) == {
        "status": "complete"
    }
    return next(payload for stage, payload in case.calls if stage == "finalize")


def test_f_handoff_finalizes_rule_engine_scope_with_only_jobs_reads(scoped_worker):
    case = scoped_worker
    before = deepcopy(case.rules["review_scope"])
    payload = _run(case)
    record = payload["review_scope"]
    assert record["status"] == "final"
    assert record["model_outcome"] == "completed"
    assert (record["known_y"], record["x"], record["sent_count"]) == (2, 1, 1)
    assert case.reads == [f"jobs/{case.review_id}/submission.json"]
    assert case.rules["review_scope"] == before
    # Read the ledger through the test's independent moto client, never the worker stub.
    ledger = json.loads(
        case.s3.get_object(
            Bucket="reports", Key=f"reports/{case.review_id}/evidence-ledger.json"
        )["Body"].read()
    )
    assert ledger["review_scope"] == record


def test_f_skip_before_invoke_means_known_zero_sent(scoped_worker):
    case = scoped_worker
    context = SimpleNamespace(get_remaining_time_in_millis=lambda: 100_000)
    record = _run(case, context)["review_scope"]
    assert case.agent_calls == []
    assert record["model_outcome"] == "not_invoked"
    assert record["x"] == record["sent_count"] == 0
    assert all(d["sent"] is False for d in record["declarations"])
    assert [d["reason"] for d in record["declarations"]] == [
        "model_not_invoked",
        "summary_cap",
    ]


@pytest.mark.parametrize(
    "error",
    [
        ValueError("malformed output"),
        TimeoutError("runtime timeout"),
        RuntimeError("runtime error"),
    ],
)
def test_f_postfail_after_invoke_preserves_unknown_delivery(
    scoped_worker, monkeypatch, error
):
    case = scoped_worker

    def invoke(**kwargs):
        case.agent_calls.append(kwargs)
        raise error

    monkeypatch.setattr(
        worker,
        "AgentCoreRuntimeClient",
        lambda **kwargs: SimpleNamespace(invoke=invoke),
    )
    record = _run(case)["review_scope"]
    assert len(case.agent_calls) == 1
    assert record["model_outcome"] == "unknown"
    assert record["x"] is record["sent_count"] is None
    assert [d["sent"] for d in record["declarations"]] == [None, False]
    assert [d["reason"] for d in record["declarations"]] == [
        "outcome_unknown",
        "summary_cap",
    ]


@pytest.mark.parametrize("bad_scope", ["missing", None, {}, {"version": "wrong"}])
def test_f_handoff_missing_or_invalid_scope_logs_one_drop_and_completes(
    scoped_worker, capsys, bad_scope
):
    case = scoped_worker
    if bad_scope == "missing":
        del case.rules["review_scope"]
    else:
        case.rules["review_scope"] = bad_scope
    payload = _run(case)
    assert "review_scope" not in payload
    events = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("{")
    ]
    assert sum(event.get("event") == "review_scope_dropped" for event in events) == 1
    assert len(case.agent_calls) == 1


@pytest.mark.parametrize("detail", ["duplicate_resource", "duplicate_module_call"])
def test_duplicate_rejection_maps_to_malformed_configuration_without_paid_invoke(
    prepared,  # noqa: F811
    monkeypatch,
    detail,
):
    review_id, _s3, _calls, _replies, agent_calls = prepared
    stages = []

    def stage(name, payload):
        stages.append(name)
        return {
            "status": "rejected",
            "code": "malformed_configuration",
            "detail": detail,
            "reason": "Duplicate declaration",
        }

    monkeypatch.setattr(worker, "_invoke", stage)
    assert worker.handler({"review_id": review_id}, None) == {"status": "failed"}
    assert stages == ["ingest"]
    assert agent_calls == []
    item = (
        boto3.resource("dynamodb")
        .Table("reviews")
        .get_item(Key={"reviewId": review_id})["Item"]
    )
    assert item["failureCode"] == "malformed_configuration"


@pytest.mark.parametrize("with_scope", [False, True], ids=["legacy", "P0"])
def test_agentcore_payload_and_invocation_count_match_3293c1b(
    scoped_worker, with_scope
):
    case = scoped_worker
    # Valid one-bucket fixture. Expected payload keys are frozen from the
    # worker at 3293c1b, not reconstructed by calling its payload helper.
    case.rules["review_scope"] = pending_scope([declaration()])
    if not with_scope:
        case.rules.pop("review_scope")
        case.rules.pop("summary_members")
    _run(case)
    submission = next(payload for name, payload in case.calls if name == "ingest")
    expected_payload = {
        "review_id": case.review_id,
        "workload_brief": submission["workload_brief"],
        "baseline_answers": submission["baseline_answers"],
        "retrieval_query": submission["retrieval_query"],
        "rule_findings": case.rules["findings"],
        "deterministic_rule_version": case.rules["rule_version"],
        "terraform_resources": case.rules["resource_summary"],
    }
    assert case.agent_calls == [
        {
            "payload": expected_payload,
            "runtime_session_id": f"archibrief-review-session-{case.review_id}-0",
        }
    ]
    assert [name for name, _ in case.calls].count("rule_engine") == 1
    assert "review_scope" not in json.dumps(case.agent_calls)
    assert "summary_members" not in json.dumps(case.agent_calls)
