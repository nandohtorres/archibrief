import json
import time

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

import backend.lambdas.clarify_review.handler as handler_module
from backend.lambdas.clarify_review.handler import handler

TABLE = "archibrief-dev-reviews"


class _FakeSfnClient:
    calls: list = []
    error_code: str | None = None

    def send_task_success(self, taskToken: str, output: str) -> None:
        if _FakeSfnClient.error_code:
            raise ClientError(
                {"Error": {"Code": _FakeSfnClient.error_code}}, "SendTaskSuccess"
            )
        _FakeSfnClient.calls.append({"taskToken": taskToken, "output": output})


def _event(review_id: str | None, body: dict | None) -> dict:
    return {
        "headers": {"x-admin-key": "admin-secret"},
        "pathParameters": {"reviewId": review_id} if review_id else {},
        "body": json.dumps(body) if body is not None else None,
    }


def _waiting(review_id: str = "r1", token: str = "token-1") -> dict:
    return {
        "reviewId": review_id,
        "status": "needs_clarification",
        "clarificationTaskToken": token,
        "ttl": int(time.time()) + 86400,
    }


@pytest.fixture
def table(monkeypatch):
    # Real DynamoDB semantics (moto) so the conditional claim is exercised,
    # not a permissive fake. boto3.client is patched only for Step Functions.
    with mock_aws():
        monkeypatch.setenv("ADMIN_KEY", "admin-secret")
        monkeypatch.setenv("USAGE_COUNTERS_TABLE_NAME", "counters")
        boto3.resource("dynamodb", region_name="us-east-1").create_table(
            TableName="counters",
            KeySchema=[{"AttributeName": "counterKey", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "counterKey", "AttributeType": "S"}
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        t = boto3.resource("dynamodb", region_name="us-east-1").create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "reviewId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "reviewId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        monkeypatch.setenv("REVIEWS_TABLE_NAME", TABLE)
        monkeypatch.setattr(handler_module, "paid_work_allowed", lambda: True)
        _FakeSfnClient.calls = []
        _FakeSfnClient.error_code = None
        original_client = boto3.client
        monkeypatch.setattr(
            handler_module.boto3,
            "client",
            lambda service, *a, **kw: (
                _FakeSfnClient()
                if service == "stepfunctions"
                else original_client(service, *a, **kw)
            ),
        )
        yield t


def _stored(table, review_id: str = "r1") -> dict:
    return table.get_item(Key={"reviewId": review_id})["Item"]


def test_resumes_paused_execution_and_clears_token(table):
    table.put_item(Item=_waiting())

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
    stored = _stored(table)
    assert "clarificationTaskToken" not in stored
    assert stored["status"] == "pending"


def test_does_not_overwrite_fields_written_by_others(table):
    # Writing back a whole-item snapshot read before resuming would wipe
    # fields written in between.
    table.put_item(
        Item={**_waiting(), "currentStage": "reasoning", "terraformRepoRef": "repo"}
    )

    handler(_event("r1", {"answers": {"budget_ceiling": "50000"}}), None)

    stored = _stored(table)
    assert stored["currentStage"] == "reasoning"
    assert stored["terraformRepoRef"] == "repo"


def test_second_submission_gets_409_and_does_not_resume_again(table):
    table.put_item(Item=_waiting())
    handler(_event("r1", {"answers": {"a": "1"}}), None)

    second = handler(_event("r1", {"answers": {"a": "2"}}), None)

    assert second["statusCode"] == 409
    assert len(_FakeSfnClient.calls) == 1


def test_stale_token_cannot_be_claimed(table):
    # Another request already claimed and a new pause stored a new token.
    table.put_item(Item=_waiting(token="token-2"))
    client = handler_module.DynamoDBClient(table_name=TABLE)

    claimed = handler_module._claim_token(client, "r1", "token-1")

    assert claimed is False
    assert _stored(table)["clarificationTaskToken"] == "token-2"


def test_expired_task_returns_409(table):
    table.put_item(Item=_waiting())
    _FakeSfnClient.error_code = "TaskTimedOut"

    result = handler(_event("r1", {"answers": {"a": "1"}}), None)

    assert result["statusCode"] == 409


def test_transient_resume_failure_restores_token_for_retry(table):
    table.put_item(Item=_waiting())
    _FakeSfnClient.error_code = "ThrottlingException"

    result = handler(_event("r1", {"answers": {"a": "1"}}), None)

    assert result["statusCode"] == 503
    stored = _stored(table)
    assert stored["status"] == "needs_clarification"
    assert stored["clarificationTaskToken"] == "token-1"


def test_appends_additional_notes_as_a_clarification_note(table):
    table.put_item(Item=_waiting())

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


def test_rejects_review_not_awaiting_clarification(table):
    table.put_item(
        Item={"reviewId": "r1", "status": "pending", "ttl": int(time.time()) + 86400}
    )

    result = handler(_event("r1", {"answers": {}}), None)

    assert result["statusCode"] == 409
    assert _FakeSfnClient.calls == []


def test_expired_review_cannot_resume_paid_work(table):
    table.put_item(Item={**_waiting(), "ttl": 1})
    assert handler(_event("r1", {"answers": {}}), None)["statusCode"] == 404
    assert _FakeSfnClient.calls == []


def test_returns_404_for_unknown_review(table):
    assert handler(_event("missing", {"answers": {}}), None)["statusCode"] == 404


def test_returns_400_when_answers_missing(table):
    assert handler(_event("r1", {}), None)["statusCode"] == 400


def test_returns_400_when_review_id_missing(table):
    assert handler(_event(None, {"answers": {}}), None)["statusCode"] == 400


def test_returns_400_for_invalid_json_body(table):
    result = handler({"pathParameters": {"reviewId": "r1"}, "body": "{not json"}, None)
    assert result["statusCode"] == 400


def test_kill_switch_blocks_resume_and_keeps_token(table, monkeypatch):
    # Resuming must still honor the kill switch.
    table.put_item(Item=_waiting())
    monkeypatch.setattr(handler_module, "paid_work_allowed", lambda: False)

    result = handler(_event("r1", {"answers": {"budget_ceiling": "50000"}}), None)

    assert result["statusCode"] == 503
    assert _FakeSfnClient.calls == []
    assert _stored(table)["clarificationTaskToken"] == "token-1"
