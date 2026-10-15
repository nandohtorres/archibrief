import json

import backend.lambdas.deeper_review.handler as handler_module
from backend.lambdas.deeper_review.handler import handler


class _FakeDynamoDBClient:
    def __init__(self, table_name: str):
        self.table_name = table_name

    def get_item(self, key: dict):
        return _FakeDynamoDBClient.TABLES[self.table_name].get(key["reviewId"])

    def put_item(self, item: dict) -> None:
        # Mirror DynamoDB: a write missing the table's key attributes is
        # rejected. A permissive fake hid exactly this bug (Codex F02).
        keys = _FakeDynamoDBClient.KEY_SCHEMA.get(self.table_name, [])
        missing = [k for k in keys if k not in item]
        if missing:
            raise ValueError(f"Missing the key {missing[0]} in the item")
        _FakeDynamoDBClient.PUT_ITEMS.setdefault(self.table_name, []).append(item)

    KEY_SCHEMA: dict = {"findings": ["reviewId", "findingId"]}
    TABLES: dict = {}
    PUT_ITEMS: dict = {}


class _FakeS3Client:
    def __init__(self, bucket: str):
        self.bucket = bucket

    def get_object(self, key: str) -> bytes:
        return _FakeS3Client.OBJECTS[key]

    OBJECTS: dict = {}


class _FakeAgentCoreRuntimeClient:
    response: dict = {}
    calls: list = []

    def __init__(self, agent_runtime_arn: str):
        self.agent_runtime_arn = agent_runtime_arn

    def invoke(self, payload: dict, runtime_session_id: str) -> dict:
        _FakeAgentCoreRuntimeClient.calls.append(
            {"payload": payload, "runtime_session_id": runtime_session_id}
        )
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
}


def _event(review_id: str | None, finding_id: str | None) -> dict:
    return {
        "pathParameters": {
            **({"reviewId": review_id} if review_id else {}),
            **({"findingId": finding_id} if finding_id else {}),
        }
    }


def _setup(
    monkeypatch, *, review_item: dict | None, ledger: dict | None, agent_response: dict
):
    monkeypatch.setenv("REVIEWS_TABLE_NAME", "reviews")
    monkeypatch.setenv("REPORTS_BUCKET_NAME", "reports")
    monkeypatch.setenv("FINDINGS_TABLE_NAME", "findings")
    monkeypatch.setenv(
        "AGENTCORE_RUNTIME_ARN", "arn:aws:bedrock-agentcore:us-east-1:000:runtime/x"
    )
    monkeypatch.setattr(handler_module, "DynamoDBClient", _FakeDynamoDBClient)
    monkeypatch.setattr(handler_module, "S3Client", _FakeS3Client)
    monkeypatch.setattr(
        handler_module, "AgentCoreRuntimeClient", _FakeAgentCoreRuntimeClient
    )

    _FakeDynamoDBClient.TABLES = {"reviews": {"r1": review_item} if review_item else {}}
    _FakeDynamoDBClient.PUT_ITEMS = {}
    _FakeS3Client.OBJECTS = (
        {"reports/r1/evidence-ledger.json": json.dumps(ledger).encode("utf-8")}
        if ledger
        else {}
    )
    _FakeAgentCoreRuntimeClient.response = agent_response
    _FakeAgentCoreRuntimeClient.calls = []


def test_runs_deeper_pass_and_persists_new_finding(monkeypatch):
    _setup(
        monkeypatch,
        review_item={
            "reviewId": "r1",
            "reportS3Key": "reports/r1/evidence-ledger.json",
        },
        ledger={
            "workload_brief": "a 3-tier web app on ECS",
            "findings": [
                {"finding_id": "f1", "category": "iam", "finding": "original finding"}
            ],
        },
        agent_response={"status": "complete", "findings": [_VALID_RAW_FINDING]},
    )

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
    assert _FakeAgentCoreRuntimeClient.calls[0]["payload"]["mode"] == "deeper"
    assert _FakeAgentCoreRuntimeClient.calls[0]["payload"]["parent_finding_id"] == "f1"
    assert len(_FakeAgentCoreRuntimeClient.calls[0]["runtime_session_id"]) >= 33
    assert len(_FakeDynamoDBClient.PUT_ITEMS["findings"]) == 1


def test_returns_400_when_path_params_missing(monkeypatch):
    _setup(monkeypatch, review_item=None, ledger=None, agent_response={})
    result = handler(_event(None, "f1"), None)
    assert result["statusCode"] == 400


def test_returns_404_for_unknown_review(monkeypatch):
    _setup(monkeypatch, review_item=None, ledger=None, agent_response={})
    result = handler(_event("missing", "f1"), None)
    assert result["statusCode"] == 404


def test_returns_409_when_review_has_no_report_yet(monkeypatch):
    _setup(
        monkeypatch,
        review_item={"reviewId": "r1", "status": "pending"},
        ledger=None,
        agent_response={},
    )
    result = handler(_event("r1", "f1"), None)
    assert result["statusCode"] == 409


def test_returns_404_when_finding_not_in_ledger(monkeypatch):
    _setup(
        monkeypatch,
        review_item={
            "reviewId": "r1",
            "reportS3Key": "reports/r1/evidence-ledger.json",
        },
        ledger={"workload_brief": "brief", "findings": []},
        agent_response={},
    )
    result = handler(_event("r1", "nonexistent"), None)
    assert result["statusCode"] == 404


def test_returns_409_when_workload_brief_was_never_persisted(monkeypatch):
    _setup(
        monkeypatch,
        review_item={
            "reviewId": "r1",
            "reportS3Key": "reports/r1/evidence-ledger.json",
        },
        ledger={"findings": [{"finding_id": "f1", "category": "iam", "finding": "x"}]},
        agent_response={},
    )
    result = handler(_event("r1", "f1"), None)
    assert result["statusCode"] == 409


def test_returns_502_when_agent_produces_no_valid_findings(monkeypatch):
    _setup(
        monkeypatch,
        review_item={
            "reviewId": "r1",
            "reportS3Key": "reports/r1/evidence-ledger.json",
        },
        ledger={
            "workload_brief": "brief",
            "findings": [{"finding_id": "f1", "category": "iam", "finding": "x"}],
        },
        agent_response={"status": "complete", "findings": [{"not": "a valid finding"}]},
    )
    result = handler(_event("r1", "f1"), None)
    assert result["statusCode"] == 502
