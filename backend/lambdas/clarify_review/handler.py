"""ArchiBrief Lambda: clarify_review.

Backs `POST /reviews/{reviewId}/clarify` (API Gateway v2, AWS_PROXY
Lambda integration — same reasoning as get_review.handler for why this
can't be a no-compute integration: resuming a specific paused Step
Functions execution via `SendTaskSuccess` is not one of API Gateway v2's
native AWS_PROXY quick-create integration subtypes). Path/body split
matches the documented contract (Work-Project-System-Design.md's "API
contracts" section and the frontend's lib/api.ts, both predating this
Lambda — corrected 2026-10-01 after this handler was first built against
a flat, undocumented `POST /clarify` + body `review_id` shape instead).

reviewId comes from the path (`event["pathParameters"]["reviewId"]`,
same as get_review.handler), not the body. Body is
`{"answers": {<preflight field name>: <value>, ...}, "additional_notes":
<optional string>}`. Looks up the pending clarification token that
store_clarification_token.handler wrote onto the review's DynamoDB item,
calls `states:SendTaskSuccess` to resume the paused outer state machine
execution (its StoreClarificationToken state), then clears the token so
a second call for the same review can't resume an already-resumed (or
never-paused) execution.

`answers` is returned to the state machine as the task's output under
`baseline_answers` — the outer definition merges it into
`$.baseline_answers` before re-invoking the agent, per
Work-Project-Build-Plan.md's 2026-09-17 design (Codex-reviewed:
`lambda:invoke.waitForTaskToken`, not a DynamoDB-based resume — AWS does
not support `dynamodb:updateItem.waitForTaskToken`).

`additional_notes` (added 2026-10-13) is a free-text field the frontend
shows alongside the structured per-field answers, for anything the
user wants considered that doesn't fit a known preflight field. It's
NOT merged into `answers`/`baseline_answers` — those only ever hold
values for fields `preflight_node` actually evaluates by name
(backend/agent/nodes/preflight.py's BASELINE_FIELD_POLICIES), so an
arbitrary extra key there would just be silently ignored. Instead this
handler computes `clarification_note` (empty string if no notes were
given) and returns it alongside `baseline_answers`; the ASL's
PrepareAgentInputAfterClarification state appends it onto
`workload_brief` via `States.Format`, which is the only field
reason_node's prompt actually reads.
"""

from __future__ import annotations

import json
import os
from typing import Any

import boto3

from backend.shared.clients import DynamoDBClient


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

    # Added 2026-10-13 (frontend clarify-step.tsx's shared "anything else"
    # box) — baseline_answers never actually reaches reason_node's prompt
    # (backend/agent/nodes/reason.py only reads workload_brief/
    # rule_findings/retrieved_chunks), so a free-text note here needs an
    # explicit path to the model or it would be silently stored and never
    # considered. Computed here, not in the ASL's
    # PrepareAgentInputAfterClarification Pass state, so that Pass
    # state's States.Format call can unconditionally concatenate this
    # onto workload_brief without an ASL-side conditional (Parameters
    # blocks can't express one) — empty string when no notes were given.
    additional_notes = payload.get("additional_notes")
    clarification_note = (
        f"\n\nAdditional context provided during clarification: {additional_notes}"
        if additional_notes
        else ""
    )

    table_name = os.environ["REVIEWS_TABLE_NAME"]
    client = DynamoDBClient(table_name=table_name)

    item = client.get_item({"reviewId": review_id})
    if item is None:
        return _response(404, {"error": "review not found"})

    task_token = item.get("clarificationTaskToken")
    if item.get("status") != "needs_clarification" or not task_token:
        return _response(409, {"error": "review is not awaiting clarification"})

    sfn = boto3.client("stepfunctions", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    sfn.send_task_success(
        taskToken=task_token,
        output=json.dumps({"baseline_answers": answers, "clarification_note": clarification_note}),
    )

    # Clear the token before anything else can reuse it — SendTaskSuccess
    # itself rejects a replay with a TaskTimedOut/InvalidToken error, but
    # clearing it here also lets a later GET /reviews/{reviewId} show
    # "pending" again instead of a stale "needs_clarification".
    item.pop("clarificationTaskToken", None)
    item["status"] = "pending"
    client.put_item(item)

    return _response(200, {"reviewId": review_id, "status": "pending"})
