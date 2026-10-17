"""ArchiBrief Lambda: clarify_review.

Backs `POST /reviews/{reviewId}/clarify` (API Gateway v2, AWS_PROXY
Lambda integration; HTTP API has no native integration for
`SendTaskSuccess`).

reviewId comes from the path, not the body. The body is
`{"answers": {<preflight field name>: <value>, ...}, "additional_notes":
<optional string>}`. The handler looks up the pending task token that
store_clarification_token.handler wrote onto the review's DynamoDB item,
claims it, and calls `states:SendTaskSuccess` to resume the paused
execution at its StoreClarificationToken state. Claiming clears the
token, so a second call can't resume an already-resumed (or never-paused)
execution. The pause uses `lambda:invoke.waitForTaskToken` because Step
Functions has no `dynamodb:updateItem.waitForTaskToken` integration.

`answers` goes back to the state machine as `baseline_answers`; the
ApplyClarification state merges it over earlier rounds' answers in
`$.effective.baseline_answers` before re-invoking the agent.

`additional_notes` is free text for anything that doesn't fit a known
preflight field. It is not merged into `baseline_answers`, which only
holds fields preflight evaluates by name (BASELINE_FIELD_POLICIES in
backend/agent/nodes/preflight.py) and would silently ignore anything
else. Instead the handler returns it as `clarification_note`, which
ApplyClarification appends to `$.effective.workload_brief`, the field
the Reason prompt reads. It persists for later rounds and in Finalize's
ledger.
"""

from __future__ import annotations

import json
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from backend.shared.clients import DynamoDBClient
from backend.shared.kill_switch import paid_work_allowed
from backend.shared.retention import review_is_live


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

    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "request body must be valid JSON"})

    answers = payload.get("answers")
    if not isinstance(answers, dict):
        return _response(400, {"error": "an answers object is required"})

    # The Reason prompt reads workload_brief, not baseline_answers, so the
    # note is routed there. It is built here, empty when there are no notes,
    # so ApplyClarification's States.Format can concatenate it
    # unconditionally (Parameters blocks can't express a conditional).
    additional_notes = payload.get("additional_notes")
    clarification_note = (
        f"\n\nAdditional context provided during clarification: {additional_notes}"
        if additional_notes
        else ""
    )

    table_name = os.environ["REVIEWS_TABLE_NAME"]
    client = DynamoDBClient(table_name=table_name)

    item = client.get_item({"reviewId": review_id})
    if item is None or not review_is_live(item):
        return _response(404, {"error": "review not found"})

    task_token = item.get("clarificationTaskToken")
    if item.get("status") != "needs_clarification" or not task_token:
        return _response(409, {"error": "review is not awaiting clarification"})

    # Resuming sends the review straight into paid reasoning, past the state
    # machine's own kill-switch check. The token is kept, so the visitor can
    # resubmit once the switch is off.
    if not paid_work_allowed():
        return _response(503, {"error": "Reviews are temporarily paused. Try again later."})

    # Claim the token with a conditional field-level update before resuming.
    # Resuming first and writing back a whole-item snapshot could overwrite
    # fields the resumed workflow had already written, and two concurrent
    # submits could both reach SendTaskSuccess. Only one request can win
    # this condition; the rest get a stable 409.
    if not _claim_token(client, review_id, task_token):
        return _response(409, {"error": "answers for this review were already submitted"})

    sfn = boto3.client("stepfunctions", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    try:
        sfn.send_task_success(
            taskToken=task_token,
            output=json.dumps(
                {"baseline_answers": answers, "clarification_note": clarification_note}
            ),
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in _TOKEN_GONE_ERRORS:
            return _response(409, {"error": "this review is no longer waiting for answers"})
        # Transient failure: put the token back so the visitor can retry.
        _release_token(client, review_id, task_token)
        return _response(503, {"error": "could not resume the review; please try again"})

    return _response(200, {"reviewId": review_id, "status": "pending"})


# SendTaskSuccess errors meaning the paused task can never be resumed.
_TOKEN_GONE_ERRORS = {"TaskTimedOut", "TaskDoesNotExist", "InvalidToken"}


def _claim_token(client: DynamoDBClient, review_id: str, task_token: str) -> bool:
    try:
        client.update_item(
            Key={"reviewId": review_id},
            UpdateExpression="SET #status = :pending REMOVE clarificationTaskToken",
            ConditionExpression="#status = :waiting AND clarificationTaskToken = :token",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":pending": "pending",
                ":waiting": "needs_clarification",
                ":token": task_token,
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def _release_token(client: DynamoDBClient, review_id: str, task_token: str) -> None:
    client.update_item(
        Key={"reviewId": review_id},
        UpdateExpression="SET #status = :waiting, clarificationTaskToken = :token",
        ConditionExpression="#status = :pending AND attribute_not_exists(clarificationTaskToken)",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":pending": "pending",
            ":waiting": "needs_clarification",
            ":token": task_token,
        },
    )
