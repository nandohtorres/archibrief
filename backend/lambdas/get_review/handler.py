"""ArchiBrief Lambda: get_review.

GET /reviews/{reviewId} — HTTP API v2 payload format, AWS_PROXY Lambda
integration. Required because API Gateway v2's native AWS_PROXY
quick-create integrations only support a fixed enum of services
(Step Functions, EventBridge, SQS, AppConfig, Kinesis) — DynamoDB is not
among them (confirmed directly against AWS's HTTP API integration
subtype reference, 2026-09-17), so a plain DynamoDB read cannot be a
no-compute integration on this API type.

**Corrected 2026-10-01** (see Work-Project-Issues-Log.md): this
originally returned a thin, ad-hoc subset of the reviews-table item
(reviewId/status/findingCount/reportS3Key/...) that did NOT match the
frontend's actual `ReviewReport` contract (frontend/lib/contracts.ts,
frontend/lib/api.ts's `fetchReview`) — missing `findings`
(record+presentation), `baseline_answers`, `owner_id`, etc. entirely.
Once a review is complete, this now fetches the S3 evidence ledger and
assembles the real contract shape via backend.shared.report
(build_review_report) — the same assembly deeper_review.handler's own
ledger-reading logic is modeled on. Still returns the thin pointer
subset for a review that isn't complete yet (no `ReviewReport` exists
to build — the frontend's own `fetchReview` return type is always
`ReviewReport`, but nothing in this codebase actually calls it before a
review completes yet; polling pending/needs_clarification state through
this same endpoint is unstarted frontend-side design, not solved here).
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
    # Added 2026-10-13 — the new per-stage progress tracker
    # (infra/modules/step-functions-lambda's RecordStage* states) writes
    # this directly onto the review's DynamoDB item; without it here,
    # GET /reviews/{reviewId} would silently drop the field even though
    # it's actually being written.
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
