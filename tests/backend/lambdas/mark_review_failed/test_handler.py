import json

import boto3
import pytest
from moto import mock_aws

from backend.lambdas.mark_review_failed.handler import failure_code_for, handler


def _event(status: str, review_id: str | None = "r1", error: str | None = None) -> dict:
    detail = {
        "status": status,
        "input": json.dumps({"review_id": review_id} if review_id else {}),
    }
    if error:
        detail["error"] = error
        detail["cause"] = "internal detail that must never be stored"
    return {"detail-type": "Step Functions Execution Status Change", "detail": detail}


@pytest.fixture
def table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        t = ddb.create_table(
            TableName="reviews",
            KeySchema=[{"AttributeName": "reviewId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "reviewId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield t


def test_failed_execution_marks_pending_review_failed_with_public_code(table):
    table.put_item(Item={"reviewId": "r1", "status": "pending"})

    result = handler(_event("FAILED", error="IngestRejected"), None, table=table)

    item = table.get_item(Key={"reviewId": "r1"})["Item"]
    assert result["updated"] is True
    assert item["status"] == "failed"
    assert item["failureCode"] == "invalid_archive"
    assert "internal detail" not in json.dumps(item)


def test_never_overwrites_a_completed_review(table):
    table.put_item(Item={"reviewId": "r1", "status": "complete", "reportS3Key": "k"})

    result = handler(_event("FAILED", error="States.TaskFailed"), None, table=table)

    assert result["updated"] is False
    assert table.get_item(Key={"reviewId": "r1"})["Item"]["status"] == "complete"


def test_does_not_create_an_item_for_an_unknown_review(table):
    result = handler(_event("FAILED", review_id="ghost"), None, table=table)

    assert result["updated"] is False
    assert "Item" not in table.get_item(Key={"reviewId": "ghost"})


def test_ignores_non_failure_statuses(table):
    table.put_item(Item={"reviewId": "r1", "status": "pending"})

    assert handler(_event("SUCCEEDED"), None, table=table)["updated"] is False
    assert table.get_item(Key={"reviewId": "r1"})["Item"]["status"] == "pending"


def test_input_without_review_id_is_ignored(table):
    assert (
        handler(_event("FAILED", review_id=None), None, table=table)["updated"] is False
    )


@pytest.mark.parametrize(
    ("status", "error", "code"),
    [
        ("FAILED", "IngestBlocked", "input_blocked"),
        ("FAILED", "KillSwitchActive", "paused"),
        ("FAILED", "AgentInvocationTimedOut", "timed_out"),
        ("FAILED", "ClarificationTimedOut", "clarification_expired"),
        ("FAILED", "ClarificationLimitReached", "clarification_limit"),
        ("FAILED", "Lambda.Unknown", "internal_error"),
        ("FAILED", None, "internal_error"),
        ("TIMED_OUT", None, "timed_out"),
        ("ABORTED", None, "cancelled"),
    ],
)
def test_failure_code_mapping(status, error, code):
    assert failure_code_for(status, error) == code
