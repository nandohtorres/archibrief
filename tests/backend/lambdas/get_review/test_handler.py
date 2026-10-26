import json
import time

import backend.lambdas.get_review.handler as handler_module
from backend.lambdas.get_review.handler import handler
from tests.backend import visitor


class _FakeDynamoDBClient:
    def __init__(self, table_name: str):
        self.table_name = table_name

    def get_item(self, key: dict) -> dict | None:
        return _FakeDynamoDBClient.ITEMS.get(key["reviewId"])

    ITEMS: dict = {}


class _FakeS3Client:
    def __init__(self, bucket: str):
        self.bucket = bucket

    def get_object(self, key: str) -> bytes:
        return _FakeS3Client.OBJECTS[key]

    OBJECTS: dict = {}


def _event(review_id: str | None) -> dict:
    return {
        "headers": dict(visitor.HEADERS),
        "requestContext": visitor.REQUEST_CONTEXT,
        "pathParameters": {"reviewId": review_id} if review_id else {},
    }


def _setup(monkeypatch, items: dict, objects: dict | None = None):
    visitor.enable_public(monkeypatch)
    monkeypatch.setenv("REVIEWS_TABLE_NAME", "archibrief-dev-reviews")
    monkeypatch.setenv("REPORTS_BUCKET_NAME", "archibrief-dev-reports")
    monkeypatch.setattr(handler_module, "DynamoDBClient", _FakeDynamoDBClient)
    monkeypatch.setattr(handler_module, "S3Client", _FakeS3Client)
    _FakeDynamoDBClient.ITEMS = {
        key: {**item, **visitor.review_fields()} for key, item in items.items()
    }
    _FakeS3Client.OBJECTS = objects or {}


def test_returns_pending_pointer_subset_for_incomplete_review(monkeypatch):
    _setup(
        monkeypatch,
        {
            "r1": {
                "reviewId": "r1",
                "status": "needs_clarification",
                "ttl": int(time.time()) + 86400,
                "needsClarification": ["budget_ceiling"],
                "internalTaskToken": "should-never-leak",
                "clarificationTaskToken": "should-never-leak-either",
            }
        },
    )

    result = handler(_event("r1"), None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body == {
        "reviewId": "r1",
        "status": "needs_clarification",
        "needsClarification": ["budget_ceiling"],
    }
    assert "internalTaskToken" not in body
    assert "clarificationTaskToken" not in body


def test_returns_full_review_report_for_complete_review(monkeypatch):
    ledger = {
        "workload_brief": "a 3-tier app",
        "baseline_answers": [
            {
                "field": "x",
                "label": "X",
                "outcome": "answered",
                "value": "y",
                "policy_version": "v1",
            }
        ],
        "findings": [
            {
                "finding_id": "f1",
                "review_id": "r1",
                "category": "iam",
                "type": "not-observable",
                "finding": "finding text",
                "evidence": "evidence text",
                "citation": None,
                "confidence": 0.5,
                "confidence_inputs": {
                    "evidence_directness": 0.5,
                    "source_agreement": 0.5,
                    "rule_determinism": 0.5,
                },
                "risk_impact": "low",
                "recommendation": "do nothing",
                "framework_mapping": [],
                "alternatives_considered": [],
                "depth_level": "lightweight",
                "created_at": "2026-10-01T00:00:00Z",
            }
        ],
        "generated_at": "2026-10-01T00:05:00Z",
    }
    _setup(
        monkeypatch,
        {
            "r1": {
                "reviewId": "r1",
                "status": "complete",
                "ttl": int(time.time()) + 86400,
                "reportS3Key": "reports/r1/evidence-ledger.json",
                "completedAt": "2026-09-17T00:00:00Z",
            }
        },
        objects={"reports/r1/evidence-ledger.json": json.dumps(ledger).encode("utf-8")},
    )

    result = handler(_event("r1"), None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["review_id"] == "r1"
    assert body["status"] == "complete"
    assert body["baseline_answers"][0]["field"] == "x"
    assert len(body["findings"]) == 1
    assert body["findings"][0]["record"]["finding_id"] == "f1"
    assert body["findings"][0]["presentation"]["priority"] == "unknown"


def test_returns_404_for_unknown_review(monkeypatch):
    _setup(monkeypatch, {})

    result = handler(_event("missing"), None)

    assert result["statusCode"] == 404


def test_expired_review_is_hidden_before_any_ledger_read(monkeypatch):
    _setup(
        monkeypatch,
        {
            "r1": {
                "reviewId": "r1",
                "status": "complete",
                "ttl": 1,
                "reportS3Key": "not-present",
            }
        },
    )
    assert handler(_event("r1"), None)["statusCode"] == 404


def test_returns_400_when_review_id_missing(monkeypatch):
    _setup(monkeypatch, {})

    result = handler(_event(None), None)

    assert result["statusCode"] == 400


def test_running_review_includes_the_saved_diagram_preview(monkeypatch):
    graph = {
        "version": 1,
        "lanes": [],
        "nodes": [],
        "edges": [],
        "account_findings": [],
    }
    item = {
        "reviewId": "r1",
        "status": "pending",
        "currentStage": "reasoning",
        "ttl": int(time.time()) + 86400,
        "previewArchitectureKey": "jobs/r1/architecture.json",
    }
    _setup(
        monkeypatch,
        {"r1": item},
        {"jobs/r1/architecture.json": json.dumps(graph).encode()},
    )
    body = json.loads(handler(_event("r1"), None)["body"])
    assert body["architecture"] == graph
    assert "previewArchitectureKey" not in body


def test_preview_is_left_out_when_missing_or_pointing_elsewhere(monkeypatch):
    base = {"reviewId": "r1", "status": "pending", "ttl": int(time.time()) + 86400}
    _setup(
        monkeypatch,
        {"r1": {**base, "previewArchitectureKey": "jobs/r2/architecture.json"}},
    )
    assert "architecture" not in json.loads(handler(_event("r1"), None)["body"])
    _setup(
        monkeypatch,
        {"r1": {**base, "previewArchitectureKey": "jobs/r1/architecture.json"}},
    )
    # Key recorded but the object is unreadable.
    assert json.loads(handler(_event("r1"), None)["body"])["status"] == "pending"
