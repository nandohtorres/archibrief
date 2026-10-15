import json

import backend.lambdas.clarify_review.handler as handler_module
from backend.lambdas.clarify_review.handler import handler


class _FakeDynamoDBClient:
    def __init__(self, table_name: str):
        self.table_name = table_name

    def get_item(self, key: dict) -> dict | None:
        return _FakeDynamoDBClient.ITEMS.get(key["reviewId"])

    def put_item(self, item: dict) -> None:
        _FakeDynamoDBClient.ITEMS[item["reviewId"]] = item

    ITEMS: dict = {}


class _FakeSfnClient:
    calls: list = []

    def send_task_success(self, taskToken: str, output: str) -> None:
        _FakeSfnClient.calls.append({"taskToken": taskToken, "output": output})


def _event(review_id: str | None, body: dict | None) -> dict:
    return {
        "pathParameters": {"reviewId": review_id} if review_id else {},
        "body": json.dumps(body) if body is not None else None,
    }


def _setup(monkeypatch, items: dict):
    monkeypatch.setenv("REVIEWS_TABLE_NAME", "archibrief-dev-reviews")
    monkeypatch.setattr(handler_module, "DynamoDBClient", _FakeDynamoDBClient)
    monkeypatch.setattr(handler_module, "paid_work_allowed", lambda: True)
    _FakeDynamoDBClient.ITEMS = items
    _FakeSfnClient.calls = []
    monkeypatch.setattr(
        handler_module.boto3, "client", lambda *a, **kw: _FakeSfnClient()
    )


def test_resumes_paused_execution_and_clears_token(monkeypatch):
    _setup(
        monkeypatch,
        {
            "r1": {
                "reviewId": "r1",
                "status": "needs_clarification",
                "clarificationTaskToken": "token-1",
            }
        },
    )

    result = handler(_event("r1", {"answers": {"budget_ceiling": "50000"}}), None)

    assert result["statusCode"] == 200
    assert _FakeSfnClient.calls == [
        {
            "taskToken": "token-1",
            "output": json.dumps(
                {
                    "baseline_answers": {"budget_ceiling": "50000"},
                    "clarification_note": "",
                }
            ),
        }
    ]
    stored = _FakeDynamoDBClient.ITEMS["r1"]
    assert "clarificationTaskToken" not in stored
    assert stored["status"] == "pending"


def test_appends_additional_notes_as_a_clarification_note(monkeypatch):
    _setup(
        monkeypatch,
        {
            "r1": {
                "reviewId": "r1",
                "status": "needs_clarification",
                "clarificationTaskToken": "token-1",
            }
        },
    )

    result = handler(
        _event(
            "r1",
            {
                "answers": {"regulatory_data_residency": "Yes — GDPR, HIPAA"},
                "additional_notes": "Also handles EU customer PII in a second region.",
            },
        ),
        None,
    )

    assert result["statusCode"] == 200
    [call] = _FakeSfnClient.calls
    output = json.loads(call["output"])
    assert output["baseline_answers"] == {
        "regulatory_data_residency": "Yes — GDPR, HIPAA"
    }
    assert output["clarification_note"] == (
        "\n\nAdditional context provided during clarification: "
        "Also handles EU customer PII in a second region."
    )


def test_rejects_review_not_awaiting_clarification(monkeypatch):
    _setup(monkeypatch, {"r1": {"reviewId": "r1", "status": "pending"}})

    result = handler(_event("r1", {"answers": {}}), None)

    assert result["statusCode"] == 409
    assert _FakeSfnClient.calls == []


def test_returns_404_for_unknown_review(monkeypatch):
    _setup(monkeypatch, {})

    result = handler(_event("missing", {"answers": {}}), None)

    assert result["statusCode"] == 404


def test_returns_400_when_answers_missing(monkeypatch):
    _setup(monkeypatch, {})

    result = handler(_event("r1", {}), None)

    assert result["statusCode"] == 400


def test_returns_400_when_review_id_missing(monkeypatch):
    _setup(monkeypatch, {})

    result = handler(_event(None, {"answers": {}}), None)

    assert result["statusCode"] == 400


def test_returns_400_for_invalid_json_body(monkeypatch):
    _setup(monkeypatch, {})

    result = handler({"pathParameters": {"reviewId": "r1"}, "body": "{not json"}, None)

    assert result["statusCode"] == 400


def test_kill_switch_blocks_resume_and_keeps_token(monkeypatch):
    # Regression (Codex F08): resuming skipped the kill switch and went
    # straight into paid reasoning.
    item = {
        "reviewId": "r1",
        "status": "needs_clarification",
        "clarificationTaskToken": "token-1",
    }
    _setup(monkeypatch, {"r1": item})
    monkeypatch.setattr(handler_module, "paid_work_allowed", lambda: False)

    result = handler(_event("r1", {"answers": {"budget_ceiling": "50000"}}), None)

    assert result["statusCode"] == 503
    assert _FakeSfnClient.calls == []
    assert _FakeDynamoDBClient.ITEMS["r1"]["clarificationTaskToken"] == "token-1"
