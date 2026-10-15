import boto3
from moto import mock_aws

from backend.shared.clients import S3Client


@mock_aws
def test_generate_presigned_post_returns_url_and_fields_with_size_condition():
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="archibrief-dev-test")
    client = S3Client(bucket="archibrief-dev-test", region_name="us-east-1")

    presigned = client.generate_presigned_post(
        key="uploads/r1/archive.tar", max_bytes=10 * 1024 * 1024
    )

    assert "url" in presigned
    assert presigned["fields"]["key"] == "uploads/r1/archive.tar"
    assert "policy" in presigned["fields"]


@mock_aws
def test_generate_presigned_post_defaults_content_type_to_tar():
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="archibrief-dev-test")
    client = S3Client(bucket="archibrief-dev-test", region_name="us-east-1")

    presigned = client.generate_presigned_post(key="uploads/r2/archive.tar", max_bytes=1024)

    assert presigned["fields"]["Content-Type"] == "application/x-tar"
