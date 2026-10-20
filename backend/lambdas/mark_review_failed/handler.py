"""ArchiBrief Lambda: mark-review-failed.

Triggered by EventBridge on the review state machine's "Execution Status
Change" events (FAILED / TIMED_OUT / ABORTED). Before this, no failure
path updated the review's record, so a dead run stayed "pending" forever
and the browser couldn't tell it from a slow one (Codex F05). One
listener covers every failure path — Fail states, uncaught Lambda errors,
timeouts, and manual aborts — without a Catch on every state.

Writes only a short public failure code, never the raw error or cause
(those can carry internal stage names, paths, or input fragments; they
stay in the execution history for debugging).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError

# Step Functions error name -> public failure code the frontend maps to a
# friendly message. Anything unlisted is "internal_error".
FAILURE_CODES: dict[str, str] = {
    "IngestRejected": "invalid_archive",
    "IngestBlocked": "input_blocked",
    "KillSwitchActive": "paused",
    "AgentInvocationTimedOut": "timed_out",
    "States.Timeout": "timed_out",
    "ClarificationTimedOut": "clarification_expired",
    "ClarificationLimitReached": "clarification_limit",
}

_TERMINAL_FAILURE_STATUSES = {"FAILED", "TIMED_OUT", "ABORTED"}


def failure_code_for(status: str, error: str | None) -> str:
    if status == "TIMED_OUT":
        return "timed_out"
    if status == "ABORTED":
        return "cancelled"
    return FAILURE_CODES.get(error or "", "internal_error")


def _review_id_from(detail: dict[str, Any]) -> str | None:
    try:
        review_id = json.loads(detail.get("input") or "{}").get("review_id")
    except (json.JSONDecodeError, AttributeError):
        return None
    return review_id if isinstance(review_id, str) and review_id else None


def handler(event: dict, _context: object, table: Any | None = None) -> dict:
    detail = event.get("detail") or {}
    status = detail.get("status")
    if status not in _TERMINAL_FAILURE_STATUSES:
        return {"updated": False, "reason": f"ignored status {status!r}"}

    review_id = _review_id_from(detail)
    if review_id is None:
        print(json.dumps({"event": "mark_failed_no_review_id", "status": status}))
        return {"updated": False, "reason": "no review_id in execution input"}

    code = failure_code_for(status, detail.get("error"))
    table = table or boto3.resource("dynamodb").Table(os.environ["REVIEWS_TABLE_NAME"])
    try:
        # Only an existing, not-yet-complete review is marked: never
        # overwrite a finished report, never create a stray item.
        table.update_item(
            Key={"reviewId": review_id},
            UpdateExpression="SET #status = :failed, failureCode = :code, failedAt = :at",
            ConditionExpression="attribute_exists(reviewId) AND #status <> :complete",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":failed": "failed",
                ":code": code,
                ":at": datetime.now(UTC).isoformat(),
                ":complete": "complete",
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return {"updated": False, "reason": "review missing or already complete"}
        raise

    print(json.dumps({"event": "review_marked_failed", "review_id": review_id, "code": code}))
    return {"updated": True, "review_id": review_id, "failure_code": code}
