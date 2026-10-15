import json

import boto3
from moto import mock_aws

from backend.lambdas.create_upload.handler import handler


def _event(body: dict | None) -> dict:
    return {"body": json.dumps(body) if body is not None else None}


@mock_aws
def test_handler_returns_presigned_upload_for_a_valid_review_id(monkeypatch):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="archibrief-dev-reports")
    monkeypatch.setenv("REPORTS_BUCKET_NAME", "archibrief-dev-reports")

    result = handler(_event({"review_id": "9f8e7d6c-1234-4abc-9def-0123456789ab"}), None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["archiveKey"] == "uploads/9f8e7d6c-1234-4abc-9def-0123456789ab/archive.tar"
    assert "uploadUrl" in body
    assert body["uploadFields"]["key"] == body["archiveKey"]


@mock_aws
def test_handler_accepts_the_non_uuid_fallback_review_id_format(monkeypatch):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="archibrief-dev-reports")
    monkeypatch.setenv("REPORTS_BUCKET_NAME", "archibrief-dev-reports")

    result = handler(_event({"review_id": "review-1760123456789-a1b2c3"}), None)

    assert result["statusCode"] == 200


def test_handler_rejects_missing_review_id():
    result = handler(_event({}), None)
    assert result["statusCode"] == 400


def test_handler_rejects_invalid_json_body():
    result = handler({"body": "not json"}, None)
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
