"""Bind a reserved upload and dispatch only identifiers to Standard Step Functions."""

from __future__ import annotations

import base64
import json
import os
import time
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from backend.shared.admission import (
    AdmissionDenied,
    positive_setting,
    request_digest,
    reserve_operation,
)
from backend.shared.baseline import SUBMISSION_REQUIRED_FIELDS
from backend.shared.clients import DynamoDBClient
from backend.shared.http import JSON_HEADERS, api_handler
from backend.shared.kill_switch import paid_work_allowed
from backend.shared.public_access import capability_allowed
from backend.shared.retention import review_is_live


@api_handler
def handler(event: dict, _context: object) -> dict:
    def response(status, body):
        return {
            "statusCode": status,
            "headers": dict(JSON_HEADERS),
            "body": json.dumps(body),
        }

    try:
        raw = event.get("body") or ""
        if len(raw) > 24000:
            raise ValueError
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw, validate=True).decode()
        body = json.loads(raw)
        if not isinstance(body, dict) or set(body) - {
            "review_id",
            "archive_version_id",
            "archive_s3_key",
            "terraform_repo_ref",
            "workload_brief",
            "retrieval_query",
            "baseline_answers",
        }:
            raise ValueError
        review_id = str(uuid.UUID(body["review_id"]))
        version = body["archive_version_id"]
        if not isinstance(version, str) or not 1 <= len(version) <= 1024 or version == "null":
            raise ValueError
        brief = body["workload_brief"]
        label = body["terraform_repo_ref"]
        answers = body.get("baseline_answers", {})
        if not isinstance(brief, str) or not 1 <= len(brief.strip()) <= 4000:
            raise ValueError
        if not isinstance(label, str) or len(label) > 256:
            raise ValueError
        # The regulatory question is answered up front so the review never
        # has to stop and ask (agent/nodes/preflight.py).
        if not isinstance(answers, dict) or any(
            not isinstance(answers.get(name), str) or not answers[name].strip()
            for name in SUBMISSION_REQUIRED_FIELDS
        ):
            raise ValueError
        if (
            not isinstance(answers, dict)
            or len(answers) > 20
            or any(
                not isinstance(k, str) or len(k) > 80 or not isinstance(v, str) or len(v) > 500
                for k, v in answers.items()
            )
        ):
            raise ValueError
    except (ValueError, TypeError, KeyError, UnicodeError):
        return response(400, {"error": "invalid_submission"})
    table = DynamoDBClient(table_name=os.environ["REVIEWS_TABLE_NAME"])
    review = table.get_item({"reviewId": review_id}, consistent=True)
    if (
        not review
        or not review_is_live(review)
        or not capability_allowed(event, review, write=True)
    ):
        return response(404, {"error": "review_not_found"})
    if body.get("archive_s3_key", review["archiveKey"]) != review["archiveKey"]:
        return response(400, {"error": "upload_mismatch"})
    if not paid_work_allowed():
        return response(503, {"error": "reviews_paused"})
    now = int(time.time())
    if review.get("status") == "upload_reserved" and int(review.get("uploadExpiresAt", 0)) <= now:
        return response(410, {"error": "upload_expired"})
    payload = {
        "review_id": review_id,
        "archive_s3_key": review["archiveKey"],
        "archive_s3_version": version,
        "workload_brief": brief,
        "terraform_repo_ref": label,
        "baseline_answers": answers,
        "retrieval_query": brief,
    }
    digest = request_digest(payload)
    if review.get("inputDigest") and review["inputDigest"] != digest:
        return response(409, {"error": "operation_conflict"})
    if review.get("inputDigest") == digest and (
        review.get("pipelineStarted") or review.get("status") in {"complete", "failed"}
    ):
        return response(202, {"reviewId": review_id, "status": "pending"})
    bucket = os.environ["REPORTS_BUCKET_NAME"]
    s3 = boto3.client(
        "s3", config=Config(connect_timeout=1, read_timeout=3, retries={"total_max_attempts": 1})
    )
    try:
        head = s3.head_object(
            Bucket=bucket, Key=review["archiveKey"], VersionId=version, ChecksumMode="ENABLED"
        )
    except ClientError:
        return response(400, {"error": "upload_unavailable"})
    expected = base64.b64encode(bytes.fromhex(review["archiveSha256"])).decode()
    if (
        head.get("ContentLength") != int(review["archiveSize"])
        or head.get("ChecksumSHA256") != expected
    ):
        return response(400, {"error": "upload_mismatch"})
    try:
        reserve_operation(
            review,
            "initial",
            payload,
            positive_setting("INITIAL_RESERVE_MICRO_USD", 400000),
        )
    except AdmissionDenied as exc:
        return response(409 if "operation" in exc.code else 429, {"error": exc.code})
    key = f"jobs/{review_id}/submission.json"
    try:
        # Retries cannot replace the body of an already-dispatched submission.
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(payload).encode(),
            ContentType="application/json",
            IfNoneMatch="*",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in {"PreconditionFailed", "412"}:
            return response(503, {"error": "dispatch_unavailable"})
    try:
        table.update_item(
            Key={"reviewId": review_id},
            UpdateExpression="SET inputKey = :key, inputDigest = :digest, archiveVersionId = :version, "
            "terraformRepoRef = :label, #s = :pending",
            ConditionExpression="(#ttl > :now) AND ((attribute_not_exists(inputDigest) AND #s = :reserved AND uploadExpiresAt > :now) "
            "OR (inputDigest = :digest AND #s = :pending))",
            ExpressionAttributeNames={"#s": "status", "#ttl": "ttl"},
            ExpressionAttributeValues={
                ":key": key,
                ":digest": digest,
                ":version": version,
                ":label": label,
                ":pending": "pending",
                ":reserved": "upload_reserved",
                ":now": int(time.time()),
            },
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            latest = table.get_item({"reviewId": review_id}, consistent=True)
            if latest and review_is_live(latest) and latest.get("inputDigest") == digest:
                return response(202, {"reviewId": review_id, "status": "pending"})
            return response(409, {"error": "operation_conflict"})
        return response(503, {"error": "dispatch_unavailable"})
    try:
        boto3.client(
            "stepfunctions",
            config=Config(connect_timeout=1, read_timeout=3, retries={"total_max_attempts": 1}),
        ).start_execution(
            stateMachineArn=os.environ["STATE_MACHINE_ARN"],
            name=f"review-{review_id}",
            input=json.dumps({"review_id": review_id}, sort_keys=True),
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ExecutionAlreadyExists":
            return response(503, {"error": "dispatch_unavailable"})
    except Exception:  # noqa: BLE001 - ambiguous dispatch is retained and safely retryable
        # The same name/input is safe to retry, never with a fresh execution ID.
        return response(503, {"error": "dispatch_unavailable"})
    return response(202, {"reviewId": review_id, "status": "pending"})
