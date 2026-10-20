import pytest

import backend.lambdas.audit.handler as handler_module
from backend.lambdas.audit.handler import (
    AuditTableNotConfigured,
    build_audit_entry,
    handler,
)


class _FakeDynamoDBClient:
    PUT_ITEMS: list = []

    def __init__(self, table_name: str):
        self.table_name = table_name

    def put_item(self, item: dict) -> None:
        # Mirror the AuditLog table's key schema (infra/modules/dynamodb).
        if "auditId" not in item:
            raise ValueError("Missing the key auditId in the item")
        _FakeDynamoDBClient.PUT_ITEMS.append((self.table_name, item))


@pytest.fixture(autouse=True)
def _fake_dynamodb(monkeypatch):
    _FakeDynamoDBClient.PUT_ITEMS = []
    monkeypatch.setattr(handler_module, "DynamoDBClient", _FakeDynamoDBClient)


def test_handler_writes_audit_row_to_configured_table(monkeypatch):
    monkeypatch.setenv("AUDIT_TABLE_NAME", "archibrief-dev-audit-log")
    result = handler({"review_id": "r-1", "baseline_answers": {"traffic": "low"}}, None)

    assert result["status"] == "recorded"
    [(table, item)] = _FakeDynamoDBClient.PUT_ITEMS
    assert table == "archibrief-dev-audit-log"
    assert item["auditId"] == result["audit_id"]
    assert item["reviewId"] == "r-1"
    assert item["baselineAnswers"] == {"traffic": "low"}


def test_handler_fails_instead_of_claiming_success_without_a_table(monkeypatch):
    # Without a table it must fail, not return "recorded" and write nothing.
    monkeypatch.delenv("AUDIT_TABLE_NAME", raising=False)
    with pytest.raises(AuditTableNotConfigured):
        handler({"review_id": "r-1"}, None)
    assert _FakeDynamoDBClient.PUT_ITEMS == []


def test_build_audit_entry_defaults_optional_fields():
    entry = build_audit_entry({"review_id": "r-2"})
    assert entry.baseline_answers == {}
    assert entry.guardrails_decisions == []
    assert entry.to_item()["reviewId"] == "r-2"
