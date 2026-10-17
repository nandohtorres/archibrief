import time

import boto3
import pytest
from moto import mock_aws

from backend.shared.admission import AdmissionDenied, reserve_operation
from backend.shared.clients import DynamoDBClient


@pytest.fixture
def counters(monkeypatch):
    with mock_aws():
        monkeypatch.setenv("USAGE_COUNTERS_TABLE_NAME", "paid-counters")
        monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
        table = boto3.resource("dynamodb").create_table(
            TableName="paid-counters",
            KeySchema=[{"AttributeName": "counterKey", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "counterKey", "AttributeType": "S"}
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield table


def _review(name="r1", visitor="v1"):
    return {"reviewId": name, "visitorKey": visitor, "ttl": int(time.time()) + 3600}


def test_replay_does_not_spend_again_and_changed_payload_conflicts(counters):
    assert reserve_operation(_review(), "initial", {"input": "a"}, 400000)
    before = counters.scan()["Items"]
    assert not reserve_operation(_review(), "initial", {"input": "a"}, 400000)
    assert counters.scan()["Items"] == before
    with pytest.raises(AdmissionDenied, match="operation_conflict"):
        reserve_operation(_review(), "initial", {"input": "b"}, 400000)


def test_global_budget_is_shared_across_reviews_visitors_and_paid_paths(counters):
    reserve_operation(_review(), "initial", {}, 400000)
    reserve_operation(_review("r2", "v2"), "deeper:f1", {}, 400000)
    with pytest.raises(AdmissionDenied):
        reserve_operation(_review("r3", "v3"), "clarify:token", {}, 400000)
    assert len(counters.scan()["Items"]) == 7  # 2 claims, global, 2 visitors, 2 reviews


def test_stale_preliminary_reads_cannot_overdraw_the_last_slot(counters, monkeypatch):
    # Model four callers whose preliminary operation reads all missed. The
    # service conditions, rather than those reads, must enforce the final slot.
    # Moto is not concurrency-safe; actual parallel AWS testing remains required.
    monkeypatch.setattr(DynamoDBClient, "get_item", lambda *a, **k: None)
    monkeypatch.setenv("PAID_DAILY_MAX_REQUESTS", "1")
    admitted = 0
    for number in range(4):
        try:
            reserve_operation(_review(f"r{number}", f"v{number}"), "initial", {}, 1)
            admitted += 1
        except AdmissionDenied:
            pass
    assert admitted == 1
    global_counter = next(
        row
        for row in counters.scan()["Items"]
        if row["counterKey"].startswith("paid#global")
    )
    assert global_counter["requests"] == 1
    assert global_counter["spent"] == 1


def test_zero_limits_and_expired_reviews_fail_before_any_reservation(
    counters, monkeypatch
):
    monkeypatch.setenv("PAID_REVIEW_MAX_REQUESTS", "0")
    with pytest.raises(AdmissionDenied):
        reserve_operation(_review(), "initial", {}, 1)
    with pytest.raises(AdmissionDenied):
        reserve_operation({**_review(), "ttl": 1}, "initial", {}, 1)
    assert counters.scan()["Items"] == []
