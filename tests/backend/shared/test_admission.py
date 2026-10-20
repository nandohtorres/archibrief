import time

import boto3
import pytest
from moto import mock_aws

from backend.shared.admission import (
    AdmissionDenied,
    release_operation,
    reserve_operation,
)
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


def test_admin_uses_its_own_allowance_without_a_request_cap(counters, monkeypatch):
    monkeypatch.setenv("PAID_DAILY_BUDGET_MICRO_USD", "1")
    monkeypatch.setenv("PAID_DAILY_MAX_REQUESTS", "1")
    for number in range(5):
        reserve_operation(
            _review(f"r{number}", "admin"), "initial", {}, 400000, admin=True
        )
    rows = {row["counterKey"].split("#")[1]: row for row in counters.scan()["Items"]}
    assert "global" not in rows and "visitor" not in rows and "review" not in rows
    assert rows["admin"]["spent"] == 2000000
    assert "requests" not in rows["admin"]
    monkeypatch.setenv("PAID_ADMIN_DAILY_BUDGET_MICRO_USD", "2000000")
    with pytest.raises(AdmissionDenied):
        reserve_operation(_review("r9", "admin"), "initial", {}, 1, admin=True)


def test_release_gives_the_reservation_back_once_and_keeps_the_claim(counters):
    reserve_operation(_review(), "initial", {"input": "a"}, 400000)
    assert release_operation("r1", "initial")
    assert not release_operation("r1", "initial")
    for row in counters.scan()["Items"]:
        if row["counterKey"].startswith("paid#"):
            assert row["spent"] == 0
            assert row["requests"] == 0
    # The claim stays, so the same operation is never dispatched as new.
    assert not reserve_operation(_review(), "initial", {"input": "a"}, 400000)
    assert not release_operation("r1", "missing")


def test_release_is_a_no_op_for_claims_written_before_release_existed(counters):
    counters.put_item(
        Item={"counterKey": "operation#r1#initial", "cost": 400000, "day": "x"}
    )
    assert not release_operation("r1", "initial")
    assert (
        "released"
        not in counters.get_item(Key={"counterKey": "operation#r1#initial"})["Item"]
    )


def test_release_leaves_the_claim_unreleased_if_a_counter_expired(counters):
    reserve_operation(_review(), "initial", {}, 400000)
    expired = next(
        row["counterKey"]
        for row in counters.scan()["Items"]
        if row["counterKey"].startswith("paid#global")
    )
    counters.delete_item(Key={"counterKey": expired})
    assert not release_operation("r1", "initial")
    claim = counters.get_item(Key={"counterKey": "operation#r1#initial"})["Item"]
    assert "released" not in claim


def test_public_requests_never_touch_the_admin_allowance(counters):
    reserve_operation(_review(), "initial", {}, 400000)
    keys = {row["counterKey"].split("#")[1] for row in counters.scan()["Items"]}
    assert keys == {"r1", "global", "visitor", "review"}
