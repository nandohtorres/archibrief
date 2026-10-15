import backend.lambdas.store_clarification_token.handler as handler_module
from backend.lambdas.store_clarification_token.handler import handler


class _FakeDynamoDBClient:
    def __init__(self, table_name: str):
        self.table_name = table_name

    def get_item(self, key: dict) -> dict | None:
        return _FakeDynamoDBClient.ITEMS.get(key["reviewId"])

    def put_item(self, item: dict) -> None:
        _FakeDynamoDBClient.ITEMS[item["reviewId"]] = item

    ITEMS: dict = {}


def test_stores_token_and_pending_fields_on_existing_item(monkeypatch):
    monkeypatch.setattr(handler_module, "DynamoDBClient", _FakeDynamoDBClient)
    _FakeDynamoDBClient.ITEMS = {
        "r1": {"reviewId": "r1", "status": "pending", "createdAt": "2026-09-17T00:00:00Z"}
    }

    result = handler(
        {
            "review_id": "r1",
            "taskToken": "AAAA-token",
            "needs_clarification": ["budget_ceiling"],
            "preflight_fields": {"budget_ceiling": {"outcome": "PAUSED"}},
            "reviews_table_name": "archibrief-dev-reviews",
        },
        None,
    )

    assert result == {"reviewId": "r1", "status": "needs_clarification"}
    stored = _FakeDynamoDBClient.ITEMS["r1"]
    assert stored["status"] == "needs_clarification"
    assert stored["currentStage"] == "needs_clarification"
    assert stored["clarificationTaskToken"] == "AAAA-token"
    assert stored["needsClarification"] == ["budget_ceiling"]
    assert stored["preflightFields"] == {"budget_ceiling": {"outcome": "PAUSED"}}
    # Original fields survive — this is an update, not a replacement.
    assert stored["createdAt"] == "2026-09-17T00:00:00Z"


def test_creates_item_when_none_exists_yet(monkeypatch):
    monkeypatch.setattr(handler_module, "DynamoDBClient", _FakeDynamoDBClient)
    _FakeDynamoDBClient.ITEMS = {}

    result = handler(
        {
            "review_id": "r2",
            "taskToken": "token-2",
            "needs_clarification": [],
            "preflight_fields": {},
            "reviews_table_name": "archibrief-dev-reviews",
        },
        None,
    )

    assert result == {"reviewId": "r2", "status": "needs_clarification"}
    assert _FakeDynamoDBClient.ITEMS["r2"]["reviewId"] == "r2"
