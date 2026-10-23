import json
import time

import boto3
import pytest
from botocore.exceptions import ReadTimeoutError
from moto import mock_aws

import backend.lambdas.deeper_review.handler as handler_module
from backend.lambdas.deeper_review.handler import handler
from tests.backend import visitor

REVIEWS = "reviews"
FINDINGS = "findings"
BUCKET = "reports"
LEDGER_KEY = "reports/r1/evidence-ledger.json"
LOCK = "deeperInFlight_f1"


class _FakeAgentCoreRuntimeClient:
    response: dict = {}
    calls: list = []
    inits: list = []
    raises: Exception | None = None

    def __init__(self, agent_runtime_arn: str, read_timeout_seconds: int | None = None):
        self.agent_runtime_arn = agent_runtime_arn
        _FakeAgentCoreRuntimeClient.inits.append(read_timeout_seconds)

    def invoke(self, payload: dict, runtime_session_id: str) -> dict:
        _FakeAgentCoreRuntimeClient.calls.append(
            {"payload": payload, "runtime_session_id": runtime_session_id}
        )
        if _FakeAgentCoreRuntimeClient.raises is not None:
            raise _FakeAgentCoreRuntimeClient.raises
        return _FakeAgentCoreRuntimeClient.response


_VALID_RAW_FINDING = {
    "finding_id": "f2",
    "review_id": "r1",
    "category": "iam",
    "type": "not-observable",
    "finding": "deeper finding text",
    "evidence": "evidence text",
    "citation": None,
    "confidence": 0.7,
    "confidence_inputs": {
        "evidence_directness": 0.7,
        "source_agreement": 0.7,
        "rule_determinism": 0.0,
    },
    "risk_impact": "low",
    "recommendation": "do nothing",
    "framework_mapping": [],
    "alternatives_considered": [],
    "depth_level": "deep",
    "parent_finding_id": "f1",
}

_REVIEW = {"reviewId": "r1", "reportS3Key": LEDGER_KEY}
_LEDGER = {
    "workload_brief": "a 3-tier web app on ECS",
    "findings": [
        {"finding_id": "f1", "category": "iam", "finding": "original finding"}
    ],
}


def _event(review_id: str | None, finding_id: str | None) -> dict:
    return {
        "headers": dict(visitor.HEADERS),
        "requestContext": visitor.REQUEST_CONTEXT,
        "pathParameters": {
            **({"reviewId": review_id} if review_id else {}),
            **({"findingId": finding_id} if finding_id else {}),
        },
    }


class _Env:
    def __init__(self, reviews, findings, s3):
        self.reviews = reviews
        self.findings = findings
        self.s3 = s3

    def seed(
        self, review_item: dict | None = _REVIEW, ledger: dict | None = _LEDGER
    ) -> None:
        if review_item:
            self.reviews.put_item(
                Item={
                    "ttl": int(time.time()) + 86400,
                    **visitor.review_fields(),
                    **review_item,
                }
            )
        if ledger:
            self.s3.put_object(
                Bucket=BUCKET, Key=LEDGER_KEY, Body=json.dumps(ledger).encode()
            )

    def review(self) -> dict:
        return self.reviews.get_item(Key={"reviewId": "r1"})["Item"]

    def stored_findings(self) -> list[dict]:
        return self.findings.scan()["Items"]


@pytest.fixture
def env(monkeypatch):
    # moto, not permissive fakes, so key schemas and the conditional
    # in-flight claim are really evaluated.
    with mock_aws():
        visitor.enable_public(monkeypatch)
        monkeypatch.setenv("USAGE_COUNTERS_TABLE_NAME", "counters")
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="counters",
            KeySchema=[{"AttributeName": "counterKey", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "counterKey", "AttributeType": "S"}
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        reviews = ddb.create_table(
            TableName=REVIEWS,
            KeySchema=[{"AttributeName": "reviewId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "reviewId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        findings = ddb.create_table(
            TableName=FINDINGS,
            KeySchema=[
                {"AttributeName": "reviewId", "KeyType": "HASH"},
                {"AttributeName": "findingId", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "reviewId", "AttributeType": "S"},
                {"AttributeName": "findingId", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=BUCKET)

        monkeypatch.setenv("REVIEWS_TABLE_NAME", REVIEWS)
        monkeypatch.setenv("FINDINGS_TABLE_NAME", FINDINGS)
        monkeypatch.setenv("REPORTS_BUCKET_NAME", BUCKET)
        monkeypatch.setenv(
            "AGENTCORE_RUNTIME_ARN", "arn:aws:bedrock-agentcore:us-east-1:000:runtime/x"
        )
        monkeypatch.setattr(handler_module, "paid_work_allowed", lambda: True)
        monkeypatch.setattr(
            handler_module, "AgentCoreRuntimeClient", _FakeAgentCoreRuntimeClient
        )
        _FakeAgentCoreRuntimeClient.response = {
            "status": "complete",
            "findings": [_VALID_RAW_FINDING],
        }
        _FakeAgentCoreRuntimeClient.calls = []
        _FakeAgentCoreRuntimeClient.inits = []
        _FakeAgentCoreRuntimeClient.raises = None
        yield _Env(reviews, findings, s3)


def test_runs_deeper_pass_and_persists_new_finding(env):
    env.seed()

    result = handler(_event("r1", "f1"), None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["parentFindingId"] == "f1"
    assert len(body["findings"]) == 1
    # Same {record, presentation} shape build_review_report uses, so the
    # frontend can render this through the normal ReportFinding display.
    assert (
        body["findings"][0]["record"]["finding_id"] == _VALID_RAW_FINDING["finding_id"]
    )
    assert body["findings"][0]["presentation"]["priority"]
    assert body["findings"][0]["presentation"]["short_label"]
    call = _FakeAgentCoreRuntimeClient.calls[0]
    assert call["payload"]["mode"] == "deeper"
    assert call["payload"]["parent_finding_id"] == "f1"
    assert len(call["runtime_session_id"]) >= 33
    assert len(env.stored_findings()) == 1
    # The in-flight claim is released after a successful run.
    assert LOCK not in env.review()


def test_agent_read_timeout_is_under_the_gateway_limit(env):
    # HTTP API cuts a Lambda integration at 30s.
    env.seed()
    handler(_event("r1", "f1"), None)
    assert _FakeAgentCoreRuntimeClient.inits == [
        handler_module.AGENT_READ_TIMEOUT_SECONDS
    ]
    assert handler_module.AGENT_READ_TIMEOUT_SECONDS < 28


def test_repeat_request_returns_stored_result_without_a_second_paid_run(env):
    # A retry or double-click must not re-invoke the agent.
    env.seed()
    first = handler(_event("r1", "f1"), None)

    second = handler(_event("r1", "f1"), None)

    assert second["statusCode"] == 200
    assert len(_FakeAgentCoreRuntimeClient.calls) == 1
    assert (
        json.loads(second["body"])["findings"] == json.loads(first["body"])["findings"]
    )


def test_concurrent_request_gets_409_while_a_run_is_in_flight(env):
    env.seed(review_item={**_REVIEW, LOCK: int(time.time())})

    result = handler(_event("r1", "f1"), None)

    assert result["statusCode"] == 409
    assert _FakeAgentCoreRuntimeClient.calls == []


def test_stale_in_flight_claim_is_taken_over(env):
    stale = int(time.time()) - handler_module.IN_FLIGHT_STALE_SECONDS - 5
    env.seed(review_item={**_REVIEW, LOCK: stale})

    result = handler(_event("r1", "f1"), None)

    assert result["statusCode"] == 200
    assert len(_FakeAgentCoreRuntimeClient.calls) == 1


def test_agent_timeout_returns_504_and_keeps_the_claim(env):
    env.seed()
    _FakeAgentCoreRuntimeClient.raises = ReadTimeoutError(
        endpoint_url="https://agentcore"
    )

    result = handler(_event("r1", "f1"), None)

    assert result["statusCode"] == 504
    # Kept so an immediate retry can't start a second run while the first
    # may still be going; it expires after IN_FLIGHT_STALE_SECONDS.
    assert LOCK in env.review()
    assert handler(_event("r1", "f1"), None)["statusCode"] == 409


def test_unexpected_agent_error_releases_the_claim(env):
    env.seed()
    _FakeAgentCoreRuntimeClient.raises = RuntimeError("boom")

    with pytest.raises(RuntimeError):
        handler(_event("r1", "f1"), None)

    assert LOCK not in env.review()


def test_returns_400_when_path_params_missing(env):
    assert handler(_event(None, "f1"), None)["statusCode"] == 400


def test_returns_404_for_unknown_review(env):
    assert handler(_event("missing", "f1"), None)["statusCode"] == 404


def test_returns_409_when_review_has_no_report_yet(env):
    env.seed(review_item={"reviewId": "r1", "status": "pending"}, ledger=None)
    assert handler(_event("r1", "f1"), None)["statusCode"] == 409


def test_returns_404_when_finding_not_in_ledger(env):
    env.seed(ledger={"workload_brief": "brief", "findings": []})
    assert handler(_event("r1", "nonexistent"), None)["statusCode"] == 404


def test_returns_409_when_workload_brief_was_never_persisted(env):
    env.seed(
        ledger={"findings": [{"finding_id": "f1", "category": "iam", "finding": "x"}]}
    )
    assert handler(_event("r1", "f1"), None)["statusCode"] == 409


def test_returns_502_when_agent_produces_no_valid_findings(env):
    env.seed()
    _FakeAgentCoreRuntimeClient.response = {
        "status": "complete",
        "findings": [{"not": "a valid finding"}],
    }

    result = handler(_event("r1", "f1"), None)

    assert result["statusCode"] == 502
    assert LOCK not in env.review()


def test_kill_switch_blocks_deeper_before_any_paid_call(env, monkeypatch):
    # Deeper review invokes AgentCore directly, outside the state machine's
    # kill-switch check, so it must check the kill switch itself.
    env.seed()
    monkeypatch.setattr(handler_module, "paid_work_allowed", lambda: False)

    result = handler(_event("r1", "f1"), None)

    assert result["statusCode"] == 503
    assert _FakeAgentCoreRuntimeClient.calls == []


def test_expired_review_cannot_serve_cached_or_new_deeper_findings(env):
    env.seed(review_item={**_REVIEW, "ttl": 1})
    assert handler(_event("r1", "f1"), None)["statusCode"] == 404
    assert _FakeAgentCoreRuntimeClient.calls == []


def test_new_deeper_findings_share_the_original_review_expiry(env):
    env.seed()
    assert handler(_event("r1", "f1"), None)["statusCode"] == 200
    assert all(item["ttl"] == env.review()["ttl"] for item in env.stored_findings())
