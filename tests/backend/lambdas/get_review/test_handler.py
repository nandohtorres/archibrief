import json

import backend.lambdas.get_review.handler as handler_module
from backend.lambdas.get_review.handler import handler


class _FakeDynamoDBClient:
    def __init__(self, table_name: str):
        self.table_name = table_name

    def get_item(self, key: dict) -> dict | None:
        return _FakeDynamoDBClient.ITEMS.get(key["reviewId"])

    ITEMS: dict = {}


def _event(review_id: str | None) -> dict:
    return {"pathParameters": {"reviewId": review_id} if review_id else {}}


def test_returns_allowlisted_fields_for_complete_review(monkeypatch):
    monkeypatch.setenv("REVIEWS_TABLE_NAME", "archibrief-dev-reviews")
    monkeypatch.setattr(handler_module, "DynamoDBClient", _FakeDynamoDBClient)
    _FakeDynamoDBClient.ITEMS = {
        "r1": {
            "reviewId": "r1",
            "status": "complete",
            "findingCount": 3,
            "reportS3Key": "reports/r1/evidence-ledger.json",
            "completedAt": "2026-09-17T00:00:00Z",
            "internalTaskToken": "should-never-leak",
        }
    }

    result = handler(_event("r1"), None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body == {
        "reviewId": "r1",
        "status": "complete",
        "findingCount": 3,
        "reportS3Key": "reports/r1/evidence-ledger.json",
        "completedAt": "2026-09-17T00:00:00Z",
    }
    assert "internalTaskToken" not in body


def test_returns_404_for_unknown_review(monkeypatch):
    monkeypatch.setenv("REVIEWS_TABLE_NAME", "archibrief-dev-reviews")
    monkeypatch.setattr(handler_module, "DynamoDBClient", _FakeDynamoDBClient)
    _FakeDynamoDBClient.ITEMS = {}

    result = handler(_event("missing"), None)

    assert result["statusCode"] == 404


def test_returns_400_when_review_id_missing(monkeypatch):
    monkeypatch.setenv("REVIEWS_TABLE_NAME", "archibrief-dev-reviews")

    result = handler(_event(None), None)

    assert result["statusCode"] == 400
