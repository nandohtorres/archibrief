"""ArchiBrief Lambda: get_review.

GET /reviews/{reviewId}: HTTP API v2 payload format, AWS_PROXY Lambda
integration. A Lambda is needed because HTTP API's native service
integrations cover only Step Functions, EventBridge, SQS, AppConfig and
Kinesis, not DynamoDB.

For a complete review, fetches the S3 evidence ledger and assembles the
frontend's `ReviewReport` contract (frontend/lib/contracts.ts) via
backend.shared.report.build_review_report. For a review that is not
complete yet, returns only an allowlisted subset of the reviews-table
item (status, progress, clarification and failure fields).
"""

from __future__ import annotations

import json
import os
from typing import Any

from backend.shared.clients import DynamoDBClient, S3Client
from backend.shared.report import build_review_report

_PENDING_ALLOWED_FIELDS = (
    "reviewId",
    "status",
    "findingCount",
    "reportS3Key",
    "completedAt",
    "createdAt",
    "needsClarification",
    "preflightFields",
    # Set by mark_review_failed: a short public code, never the raw Step
    # Functions error/cause.
    "failureCode",
    "failedAt",
    # Per-stage progress, written by the RecordStage* states in
    # infra/modules/step-functions-lambda.
    "currentStage",
)


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def handler(event: dict, _context: object) -> dict:
    review_id = (event.get("pathParameters") or {}).get("reviewId")
    if not review_id:
        return _response(400, {"error": "reviewId path parameter is required"})

    reviews_table = os.environ["REVIEWS_TABLE_NAME"]
    item = DynamoDBClient(table_name=reviews_table).get_item({"reviewId": review_id})

    if item is None:
        return _response(404, {"error": "review not found"})

    report_s3_key = item.get("reportS3Key")
    if item.get("status") != "complete" or not report_s3_key:
        public_item = {k: item[k] for k in _PENDING_ALLOWED_FIELDS if k in item}
        return _response(200, public_item)

    reports_bucket = os.environ["REPORTS_BUCKET_NAME"]
    ledger = json.loads(S3Client(bucket=reports_bucket).get_object(report_s3_key))
    return _response(200, build_review_report(item, ledger))
