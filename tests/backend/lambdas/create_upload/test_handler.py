import json

import boto3
import pytest
from moto import mock_aws

from backend.lambdas.create_upload.handler import handler


def _event(body: dict | None) -> dict:
    return {
        "headers": {"x-admin-key": "admin-secret"},
        "body": json.dumps(body) if body is not None else None,
    }


def _configure(monkeypatch):
    monkeypatch.setenv("ADMIN_KEY", "admin-secret")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("REVIEWS_TABLE_NAME", "reviews")
    monkeypatch.setenv("USAGE_COUNTERS_TABLE_NAME", "counters")
    monkeypatch.setenv("REPORTS_BUCKET_NAME", "archibrief-dev-reports")
    for table, key in (("reviews", "reviewId"), ("counters", "counterKey")):
        boto3.client("dynamodb", region_name="us-east-1").create_table(
            TableName=table,
            KeySchema=[{"AttributeName": key, "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": key, "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )


@mock_aws
def test_handler_issues_its_own_id_and_conditional_checksum_bound_upload(monkeypatch):
    boto3.client("s3", region_name="us-east-1").create_bucket(
        Bucket="archibrief-dev-reports"
    )
    _configure(monkeypatch)

    result = handler(_event({"archive_size": 100, "archive_sha256": "a" * 64}), None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["archiveKey"] == f"uploads/{body['reviewId']}/archive.tar"
    assert "uploadUrl" in body
    assert body["uploadMethod"] == "PUT"
    assert body["uploadHeaders"]["If-None-Match"] == "*"
    stored = (
        boto3.resource("dynamodb")
        .Table("reviews")
        .get_item(Key={"reviewId": body["reviewId"]})["Item"]
    )
    assert "readToken" not in stored and "writeToken" not in stored
    assert stored["readTokenHash"] != body["readToken"]


@mock_aws
def test_handler_rejects_caller_selected_review_ids(monkeypatch):
    boto3.client("s3", region_name="us-east-1").create_bucket(
        Bucket="archibrief-dev-reports"
    )
    monkeypatch.setenv("REPORTS_BUCKET_NAME", "archibrief-dev-reports")

    result = handler(_event({"review_id": "review-1760123456789-a1b2c3"}), None)

    assert result["statusCode"] == 400


def test_handler_rejects_missing_review_id():
    result = handler(_event({}), None)
    assert result["statusCode"] == 400


def test_handler_rejects_invalid_json_body():
    result = handler({"body": "not json"}, None)
    assert result["statusCode"] == 400


@pytest.mark.parametrize("payload", [[], [1], None, True, 42, "upload"])
def test_handler_rejects_non_object_json_before_creating_an_upload(payload):
    result = handler({"body": json.dumps(payload)}, None)
    assert result["statusCode"] == 400


def test_handler_rejects_path_traversal_in_review_id():
    result = handler(_event({"review_id": "../../etc/passwd"}), None)
    assert result["statusCode"] == 400


def test_handler_rejects_review_id_with_slash():
    result = handler(_event({"review_id": "a/b"}), None)
    assert result["statusCode"] == 400


def test_handler_rejects_non_string_review_id():
    result = handler(_event({"review_id": 12345}), None)
    assert result["statusCode"] == 400
