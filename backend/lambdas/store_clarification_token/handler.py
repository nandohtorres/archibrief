"""ArchiBrief Lambda: store_clarification_token.

Called by the outer Step Functions state machine's StoreClarificationToken
state, a Task using the `arn:aws:states:::lambda:invoke.waitForTaskToken`
service integration pattern. The execution pauses at this state until
something else (the clarify_review Lambda, behind `POST /reviews/{reviewId}/clarify`) calls
`SendTaskSuccess`/`SendTaskFailure` with this same token.

This handler's only job is to make that pending token discoverable by a
later, unrelated Lambda invocation: persist it on the review's existing
DynamoDB item, alongside which preflight fields are blocking (ADR-0039's
agent/nodes/preflight.py PAUSED fields) so a UI can ask the right
question. It never resolves the task itself — resolution happens only in
clarify_review.handler, out-of-band, potentially minutes or hours later.
"""

from __future__ import annotations

from backend.shared.clients import DynamoDBClient


def handler(event: dict, _context: object) -> dict:
    review_id = event["review_id"]
    task_token = event["taskToken"]

    # Like the other Lambdas on this state machine, the table name arrives
    # as a literal ASL Parameter in the event rather than an environment
    # variable, so it is never caller-supplied input.
    table_name = event["reviews_table_name"]
    client = DynamoDBClient(table_name=table_name)

    existing = client.get_item({"reviewId": review_id}) or {"reviewId": review_id}
    existing.update(
        {
            "status": "needs_clarification",
            # currentStage mirrors status here because this Lambda writes
            # to DynamoDB itself; the other stages get currentStage from a
            # preceding RecordStage* ASL state (infra/modules/step-functions-lambda).
            "currentStage": "needs_clarification",
            "clarificationTaskToken": task_token,
            "needsClarification": event.get(
                "needs_clarification", existing.get("needsClarification", [])
            ),
            "preflightFields": event.get("preflight_fields", existing.get("preflightFields", {})),
        }
    )
    client.put_item(existing)

    return {"reviewId": review_id, "status": "needs_clarification"}
