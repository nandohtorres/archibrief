"""ArchiBrief Lambda: get_review.

GET /reviews/{reviewId} — HTTP API v2 payload format, AWS_PROXY Lambda
integration. Required because API Gateway v2's native AWS_PROXY
quick-create integrations only support a fixed enum of services
(Step Functions, EventBridge, SQS, AppConfig, Kinesis) — DynamoDB is not
among them (confirmed directly against AWS's HTTP API integration
subtype reference, 2026-09-17), so a plain DynamoDB read cannot be a
no-compute integration on this API type.

Returns an explicit ALLOWLISTED subset of the reviews-table item —
never the raw item — so a field added later for internal use (a task
token, an idempotency bookkeeping field) doesn't silently leak into a
public response just because it exists on the row.
"""

from __future__ import annotations

import json
import os
from typing import Any

from backend.shared.clients import DynamoDBClient

_ALLOWED_FIELDS = (
    "reviewId",
    "status",
    "findingCount",
    "reportS3Key",
    "completedAt",
    "createdAt",
    "question",
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

    table_name = os.environ["REVIEWS_TABLE_NAME"]
    item = DynamoDBClient(table_name=table_name).get_item({"reviewId": review_id})

    if item is None:
        return _response(404, {"error": "review not found"})

    public_item = {k: item[k] for k in _ALLOWED_FIELDS if k in item}
    return _response(200, public_item)
