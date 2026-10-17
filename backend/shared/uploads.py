"""Bounded server-issued upload reservations and immutable S3 PUT signing."""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
import time
import uuid
from datetime import UTC, datetime

import boto3
from botocore.config import Config

from backend.shared.admission import AdmissionDenied, positive_setting
from backend.shared.clients import DynamoDBTransactionClient, TransactionCanceled
from backend.shared.http import api_handler
from backend.shared.public_access import is_admin, token_hash, verify_upload_challenge
from backend.shared.retention import REVIEW_LIFETIME_SECONDS

MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
UPLOAD_LEASE_SECONDS = 900


def reserve_upload(event: dict, payload: dict) -> dict:
    if set(payload) - {"archive_size", "archive_sha256", "turnstile_token"}:
        raise ValueError("unsupported upload fields")
    size, digest = payload.get("archive_size"), payload.get("archive_sha256")
    if type(size) is not int or not 1 <= size <= MAX_ARCHIVE_BYTES:
        raise ValueError("archive_size must be between 1 and 20971520 bytes")
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("archive_sha256 must be a lowercase SHA-256 digest")
    visitor = verify_upload_challenge(event, payload.get("turnstile_token", ""))
    now = int(time.time())
    day = datetime.fromtimestamp(now, UTC).strftime("%Y%m%d")
    review_id = str(uuid.uuid4())
    read_token, write_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
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
    table = os.environ.get("USAGE_COUNTERS_TABLE_NAME")
    reviews = os.environ.get("REVIEWS_TABLE_NAME")
    bucket = os.environ.get("REPORTS_BUCKET_NAME")
    if not table or not reviews or not bucket:
        raise AdmissionDenied("admission_unavailable")
    actions = [
        {
            "Put": {
                "TableName": reviews,
                "Item": review,
                "ConditionExpression": "attribute_not_exists(reviewId)",
            }
        }
    ]
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
    checksum = base64.b64encode(bytes.fromhex(digest)).decode()
    signed_headers = {
        "Content-Type": "application/x-tar",
        "If-None-Match": "*",
        "x-amz-checksum-sha256": checksum,
        "x-amz-sdk-checksum-algorithm": "SHA256",
    }
    # Conditional PUT prevents replaying the URL to create more object versions.
    # The exact length/checksum are signed; S3 validates the digest on upload.
    url = boto3.client("s3", config=Config(signature_version="s3v4")).generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket,
            "Key": archive_key,
            "ContentLength": size,
            "ContentType": "application/x-tar",
            "IfNoneMatch": "*",
            "ChecksumSHA256": checksum,
            "ChecksumAlgorithm": "SHA256",
        },
        ExpiresIn=UPLOAD_LEASE_SECONDS,
    )
    return {
        "reviewId": review_id,
        "archiveKey": archive_key,
        "uploadUrl": url,
        "uploadMethod": "PUT",
        "uploadHeaders": signed_headers,
        "readToken": read_token,
        "writeToken": write_token,
        "uploadExpiresAt": review["uploadExpiresAt"],
        "expiresAt": review["ttl"],
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
        if exc.code in {"admission_unavailable", "challenge_unavailable"}:
            status = 503
        return response(status, {"error": exc.code})
