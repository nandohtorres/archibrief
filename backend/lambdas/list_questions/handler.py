"""ArchiBrief Lambda: list_questions.

GET /reviews/{reviewId}/questions — a review's chat transcript, the
suggested questions (and whether each is already answered, so free), and
how many questions are left (ADR-0050). No model call, no cost.

Expired questions are left out even before DynamoDB's TTL deletes them,
since TTL deletion can lag by days.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from backend.chat.access import (
    FINAL_STATUSES,
    caller_allowed,
    question_is_live,
    questions_per_review,
    transcript_item,
)
from backend.chat.context import build_review_context
from backend.chat.suggested import suggested_questions
from backend.shared.clients import DynamoDBClient, S3Client
from backend.shared.http import JSON_HEADERS, api_handler
from backend.shared.public_access import capability_allowed
from backend.shared.retention import review_is_live

_REVIEW_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": dict(JSON_HEADERS),
        "body": json.dumps(body),
    }


@api_handler
def handler(event: dict, _context: object) -> dict:
    if not caller_allowed():
        return _response(403, {"error": "chat_not_public"})
    review_id = (event.get("pathParameters") or {}).get("reviewId", "")
    if not isinstance(review_id, str) or not _REVIEW_ID.fullmatch(review_id):
        return _response(400, {"error": "invalid_request"})

    review = DynamoDBClient(table_name=os.environ["REVIEWS_TABLE_NAME"]).get_item(
        {"reviewId": review_id}
    )
    if review is None or not review_is_live(review) or not capability_allowed(event, review):
        return _response(404, {"error": "review_not_found"})
    if review.get("status") != "complete" or not review.get("reportS3Key"):
        return _response(409, {"error": "review_not_complete"})

    now = time.time()
    items = DynamoDBClient(table_name=os.environ["QUESTIONS_TABLE_NAME"]).query(
        KeyConditionExpression="reviewId = :r",
        ExpressionAttributeValues={":r": review_id},
    )
    live = [i for i in items if question_is_live(i, now)]
    questions = sorted(
        (
            i
            for i in live
            if i["questionKey"].startswith("Q#") and i.get("status") in FINAL_STATUSES
        ),
        key=lambda i: (int(i.get("createdAt", 0)), str(i.get("askedAt", ""))),
    )
    answered_suggestions = {
        i["questionKey"][2:]
        for i in live
        if i["questionKey"].startswith("S#") and i.get("status") in FINAL_STATUSES
    }

    ledger = json.loads(
        S3Client(bucket=os.environ["REPORTS_BUCKET_NAME"]).get_object(review["reportS3Key"])
    )
    suggestions = [
        {"id": s["id"], "question": s["question"], "answered": s["id"] in answered_suggestions}
        for s in suggested_questions(build_review_context(ledger))
    ]

    limit = questions_per_review()
    return _response(
        200,
        {
            "review_id": review_id,
            "questions": [transcript_item(i) for i in questions],
            "suggested": suggestions,
            "questions_remaining": max(0, limit - int(review.get("questionsUsed", 0))),
            "limit": limit,
        },
    )
