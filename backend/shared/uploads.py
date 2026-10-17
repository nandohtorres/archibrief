"""Bounded server-issued upload reservations and immutable S3 PUT signing."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from datetime import UTC, datetime

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from backend.shared.admission import AdmissionDenied, positive_setting, request_digest
from backend.shared.clients import DynamoDBClient, DynamoDBTransactionClient, TransactionCanceled
from backend.shared.http import api_handler
from backend.shared.public_access import (
    is_admin,
    public_enabled,
    token_hash,
    verify_upload_challenge,
    visitor_key,
)
from backend.shared.retention import REVIEW_LIFETIME_SECONDS, review_is_live

MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
UPLOAD_LEASE_SECONDS = 900


def reserve_upload(event: dict, payload: dict) -> dict:
    if set(payload) - {"archive_size", "archive_sha256", "turnstile_token", "client_request_id"}:
        raise ValueError("unsupported upload fields")
    size, digest = payload.get("archive_size"), payload.get("archive_sha256")
    if type(size) is not int or not 1 <= size <= MAX_ARCHIVE_BYTES:
        raise ValueError("archive_size must be between 1 and 20971520 bytes")
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("archive_sha256 must be a lowercase SHA-256 digest")
    if not is_admin(event) and not public_enabled():
        raise AdmissionDenied("public_access_closed")
    try:
        nonce = str(
            uuid.UUID(
                payload.get("client_request_id") or (str(uuid.uuid4()) if is_admin(event) else "")
            )
        )
    except (ValueError, TypeError):
        raise ValueError("a client_request_id UUID is required") from None
    secret = os.environ.get("RESERVATION_KEY", "")
    table = os.environ.get("USAGE_COUNTERS_TABLE_NAME")
    reviews = os.environ.get("REVIEWS_TABLE_NAME")
    bucket = os.environ.get("REPORTS_BUCKET_NAME")
    if len(secret) < 32 or not table or not reviews or not bucket:
        raise AdmissionDenied("admission_unavailable")
    visitor = visitor_key(event)
    claim_key = {"counterKey": f"upload-grant#{visitor}#{token_hash(nonce)}"}
    digest_id = request_digest({"archive_size": size, "archive_sha256": digest})
    existing = DynamoDBClient(table_name=table).get_item(claim_key, consistent=True)
    if existing:
        if existing.get("digest") != digest_id:
            raise AdmissionDenied("operation_conflict")
        review = DynamoDBClient(table_name=reviews).get_item(
            {"reviewId": existing["reviewId"]}, consistent=True
        )
        if not review or not review_is_live(review):
            raise AdmissionDenied("upload_expired")
        return _grant_response(review, nonce, secret, bucket, recovered=True)
    verify_upload_challenge(event, payload.get("turnstile_token", ""))
    now = int(time.time())
    day = datetime.fromtimestamp(now, UTC).strftime("%Y%m%d")
    review_id = str(uuid.UUID(hex=_derive(secret, "id", visitor + ":" + nonce)[:32], version=4))
    read_token = _derive(secret, "read", review_id + ":" + nonce)
    write_token = _derive(secret, "write", review_id + ":" + nonce)
    archive_key = f"uploads/{review_id}/archive.tar"
    review = {
        "reviewId": review_id,
        "status": "upload_reserved",
        "visitorKey": visitor,
        "readTokenHash": token_hash(read_token),
        "writeTokenHash": token_hash(write_token),
        "archiveKey": archive_key,
        "archiveSize": size,
        "archiveSha256": digest,
        "uploadExpiresAt": now + UPLOAD_LEASE_SECONDS,
        "createdAt": datetime.fromtimestamp(now, UTC).isoformat(),
        "ttl": now + REVIEW_LIFETIME_SECONDS,
    }
    actions = [
        {
            "Put": {
                "TableName": reviews,
                "Item": review,
                "ConditionExpression": "attribute_not_exists(reviewId)",
            }
        }
    ]
    actions.append(
        {
            "Put": {
                "TableName": table,
                "Item": {
                    **claim_key,
                    "reviewId": review_id,
                    "digest": digest_id,
                    "ttl": review["ttl"],
                },
                "ConditionExpression": "attribute_not_exists(counterKey)",
            }
        }
    )
    for key, maximum in (
        (f"uploads#global#{day}", positive_setting("UPLOADS_DAILY_MAX", 100)),
        (
            f"uploads#visitor#{visitor}#{day}",
            positive_setting(
                "UPLOADS_ADMIN_DAILY_MAX" if is_admin(event) else "UPLOADS_VISITOR_DAILY_MAX",
                100 if is_admin(event) else 1,
            ),
        ),
    ):
        actions.append(
            {
                "Update": {
                    "TableName": table,
                    "Key": {"counterKey": key},
                    "UpdateExpression": "SET requests = if_not_exists(requests, :zero) + :one, #ttl = :ttl",
                    "ConditionExpression": "attribute_not_exists(requests) OR requests < :maximum",
                    "ExpressionAttributeNames": {"#ttl": "ttl"},
                    "ExpressionAttributeValues": {
                        ":zero": 0,
                        ":one": 1,
                        ":maximum": maximum,
                        ":ttl": now + 172800,
                    },
                }
            }
        )
    try:
        DynamoDBTransactionClient().transact_write(actions)
    except TransactionCanceled:
        raise AdmissionDenied("upload_limit_reached") from None
    return _grant_response(review, nonce, secret, bucket)


def _derive(secret: str, purpose: str, context: str) -> str:
    return hmac.new(
        secret.encode(), (purpose + "\0" + context).encode(), hashlib.sha256
    ).hexdigest()


def _grant_response(
    review: dict, nonce: str, secret: str, bucket: str, recovered: bool = False
) -> dict:
    review_id = review["reviewId"]
    read_token = _derive(secret, "read", review_id + ":" + nonce)
    write_token = _derive(secret, "write", review_id + ":" + nonce)
    if token_hash(write_token) != review["writeTokenHash"]:
        raise AdmissionDenied("admission_unavailable")
    remaining = int(review["uploadExpiresAt"]) - int(time.time())
    version = review.get("archiveVersionId")
    if remaining <= 0 and not version:
        raise AdmissionDenied("upload_expired")
    checksum = base64.b64encode(bytes.fromhex(review["archiveSha256"])).decode()
    client = boto3.client(
        "s3",
        config=Config(
            signature_version="s3v4",
            connect_timeout=1,
            read_timeout=3,
            retries={"total_max_attempts": 1},
        ),
    )
    if recovered and not version:
        try:
            head = client.head_object(
                Bucket=bucket, Key=review["archiveKey"], ChecksumMode="ENABLED"
            )
            if (
                head.get("ContentLength") != int(review["archiveSize"])
                or head.get("ChecksumSHA256") != checksum
            ):
                raise AdmissionDenied("upload_mismatch")
            version = head.get("VersionId")
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in {"NoSuchKey", "404", "NotFound"}:
                raise AdmissionDenied("admission_unavailable") from None
    signed_headers = {
        "Content-Type": "application/x-tar",
        "If-None-Match": "*",
        "x-amz-checksum-sha256": checksum,
        "x-amz-sdk-checksum-algorithm": "SHA256",
    }
    url = (
        client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": bucket,
                "Key": review["archiveKey"],
                "ContentLength": int(review["archiveSize"]),
                "ContentType": "application/x-tar",
                "IfNoneMatch": "*",
                "ChecksumSHA256": checksum,
                "ChecksumAlgorithm": "SHA256",
            },
            ExpiresIn=max(1, remaining),
        )
        if not version
        else ""
    )
    return {
        "reviewId": review_id,
        "archiveKey": review["archiveKey"],
        "uploadUrl": url,
        "uploadMethod": "PUT",
        "uploadHeaders": signed_headers,
        "readToken": read_token,
        "writeToken": write_token,
        "uploadExpiresAt": int(review["uploadExpiresAt"]),
        "expiresAt": int(review["ttl"]),
        **({"uploadedVersionId": version} if version else {}),
    }


@api_handler
def handler(event: dict, _context: object) -> dict:
    def response(status, body):
        return {
            "statusCode": status,
            "headers": {"content-type": "application/json", "cache-control": "no-store"},
            "body": json.dumps(body),
        }

    raw = event.get("body") or "{}"
    try:
        if len(raw) > 8192:
            raise ValueError("request body is too large")
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw, validate=True).decode()
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise TypeError("request body must be a JSON object")
        return response(200, reserve_upload(event, payload))
    except (ValueError, TypeError, UnicodeError) as exc:
        return response(
            400, {"error": str(exc) if isinstance(exc, ValueError) else "invalid request"}
        )
    except AdmissionDenied as exc:
        status = (
            403
            if exc.code in {"public_access_closed", "challenge_required", "challenge_rejected"}
            else 429
        )
        if exc.code == "operation_conflict":
            status = 409
        if exc.code == "upload_expired":
            status = 410
        if exc.code in {"admission_unavailable", "challenge_unavailable"}:
            status = 503
        return response(status, {"error": exc.code})
