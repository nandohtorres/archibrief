import base64
import hashlib
import json

import boto3
import pytest
from moto import mock_aws

from backend.lambdas.submit_review import handler as module
from backend.shared.uploads import handler as upload_handler


@pytest.fixture
def env(monkeypatch):
    with mock_aws():
        for key, value in {
            "ADMIN_KEY": "admin-secret",
            "RESERVATION_KEY": "test-" + "r" * 48,
            "AWS_DEFAULT_REGION": "us-east-1",
            "REPORTS_BUCKET_NAME": "reports",
            "REVIEWS_TABLE_NAME": "reviews",
            "USAGE_COUNTERS_TABLE_NAME": "counters",
        }.items():
            monkeypatch.setenv(key, value)
        for name, key in (("reviews", "reviewId"), ("counters", "counterKey")):
            boto3.client("dynamodb").create_table(
                TableName=name,
                KeySchema=[{"AttributeName": key, "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": key, "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )
        s3 = boto3.client("s3")
        s3.create_bucket(Bucket="reports")
        s3.put_bucket_versioning(
            Bucket="reports", VersioningConfiguration={"Status": "Enabled"}
        )
        archive = b"test archive bytes"
        event = {
            "headers": {"x-admin-key": "admin-secret"},
            "body": json.dumps(
                {
                    "archive_size": len(archive),
                    "archive_sha256": hashlib.sha256(archive).hexdigest(),
                }
            ),
        }
        upload = json.loads(upload_handler(event, None)["body"])
        version = s3.put_object(
            Bucket="reports",
            Key=upload["archiveKey"],
            Body=archive,
            ChecksumSHA256=base64.b64encode(hashlib.sha256(archive).digest()).decode(),
            ChecksumAlgorithm="SHA256",
        )["VersionId"]
        sfn = boto3.client("stepfunctions")
        arn = sfn.create_state_machine(
            name="reviews",
            definition=json.dumps(
                {"StartAt": "Done", "States": {"Done": {"Type": "Succeed"}}}
            ),
            roleArn="arn:aws:iam::123456789012:role/test",
        )["stateMachineArn"]
        monkeypatch.setenv("STATE_MACHINE_ARN", arn)
        monkeypatch.setattr(module, "paid_work_allowed", lambda: True)
        body = {
            "review_id": upload["reviewId"],
            "archive_version_id": version,
            "terraform_repo_ref": "example",
            "workload_brief": "A payments API",
        }
        yield upload, body, s3, sfn, arn


def _submit(body):
    return module.handler(
        {"headers": {"x-admin-key": "admin-secret"}, "body": json.dumps(body)}, None
    )


def test_dispatch_contains_no_submission_content_and_retry_is_idempotent(env):
    upload, body, _s3, sfn, arn = env
    result = _submit(body)
    assert result["statusCode"] == 202, result
    assert _submit(body)["statusCode"] == 202
    executions = sfn.list_executions(stateMachineArn=arn)["executions"]
    assert len(executions) == 1
    assert json.loads(
        sfn.describe_execution(executionArn=executions[0]["executionArn"])["input"]
    ) == {"review_id": upload["reviewId"]}
    counters = boto3.resource("dynamodb").Table("counters").scan()["Items"]
    # An admin submission uses the admin allowance, not the public scopes.
    assert (
        next(row for row in counters if row["counterKey"].startswith("paid#admin"))[
            "spent"
        ]
        == 400000
    )
    assert not any(row["counterKey"].startswith("paid#global") for row in counters)


def test_changed_body_and_replaced_version_cannot_dispatch_another_review(env):
    upload, body, s3, sfn, arn = env
    assert _submit(body)["statusCode"] == 202
    assert _submit({**body, "workload_brief": "changed"})["statusCode"] == 409
    new_version = s3.put_object(
        Bucket="reports", Key=upload["archiveKey"], Body=b"other"
    )["VersionId"]
    assert _submit({**body, "archive_version_id": new_version})["statusCode"] == 409
    assert len(sfn.list_executions(stateMachineArn=arn)["executions"]) == 1


def test_wrong_size_checksum_or_key_prevents_dispatch(env):
    upload, body, s3, sfn, arn = env
    version = s3.put_object(Bucket="reports", Key=upload["archiveKey"], Body=b"wrong")[
        "VersionId"
    ]
    assert _submit({**body, "archive_version_id": version})["statusCode"] == 400
    assert (
        _submit({**body, "archive_s3_key": "uploads/another/archive.tar"})["statusCode"]
        == 400
    )
    assert sfn.list_executions(stateMachineArn=arn)["executions"] == []
