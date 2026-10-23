import json

import boto3
import pytest
from moto import mock_aws

from backend.lambdas.create_upload.handler import handler
from backend.shared import uploads
from backend.shared.public_access import visitor_key
from tests.backend import visitor


def _event(body: dict | None) -> dict:
    return {
        "requestContext": visitor.REQUEST_CONTEXT,
        "body": json.dumps(body) if body is not None else None,
    }


def _configure(monkeypatch):
    monkeypatch.setenv("RESERVATION_KEY", "test-" + "r" * 48)
    visitor.enable_public(monkeypatch)
    # Turnstile is covered in test_public_access; here every token passes.
    monkeypatch.setattr(
        uploads, "verify_upload_challenge", lambda event, _token: visitor_key(event)
    )
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

    result = handler(
        _event(
            {
                "archive_size": 100,
                "archive_sha256": "a" * 64,
                "client_request_id": "0b5f2f6e-3c5d-4c43-9f0f-6e0f4ac4b2f1",
            }
        ),
        None,
    )

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


@mock_aws
def test_retry_recovers_same_grant_without_another_quota(monkeypatch):
    import uuid

    _configure(monkeypatch)
    s3 = boto3.client("s3")
    s3.create_bucket(Bucket="archibrief-dev-reports")
    payload = {
        "archive_size": 100,
        "archive_sha256": "a" * 64,
        "client_request_id": str(uuid.uuid4()),
    }
    first = json.loads(handler(_event(payload), None)["body"])
    second_result = handler(_event(payload), None)
    assert second_result["statusCode"] == 200, second_result
    second = json.loads(second_result["body"])
    for key in ("reviewId", "readToken", "writeToken", "uploadExpiresAt", "expiresAt"):
        assert first[key] == second[key]
    counters = boto3.resource("dynamodb").Table("counters").scan()["Items"]
    assert all(item["requests"] == 1 for item in counters if "requests" in item)
    conflict = handler(_event({**payload, "archive_size": 101}), None)
    assert conflict["statusCode"] == 409


@mock_aws
def test_retry_recovers_uploaded_version_after_lost_s3_response(monkeypatch):
    import base64
    import uuid

    _configure(monkeypatch)
    s3 = boto3.client("s3")
    bucket = "archibrief-dev-reports"
    s3.create_bucket(Bucket=bucket)
    s3.put_bucket_versioning(
        Bucket=bucket, VersioningConfiguration={"Status": "Enabled"}
    )
    payload = {
        "archive_size": 100,
        "archive_sha256": "a" * 64,
        "client_request_id": str(uuid.uuid4()),
    }
    first = json.loads(handler(_event(payload), None)["body"])
    version = s3.put_object(
        Bucket=bucket,
        Key=first["archiveKey"],
        Body=b"x" * 100,
        ChecksumSHA256=base64.b64encode(bytes.fromhex("a" * 64)).decode(),
        ChecksumAlgorithm="SHA256",
    )["VersionId"]
    recovered = handler(_event(payload), None)
    assert recovered["statusCode"] == 200, recovered
    assert json.loads(recovered["body"])["uploadedVersionId"] == version
    assert json.loads(recovered["body"])["uploadUrl"] == ""
