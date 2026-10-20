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

    # Found 2026-10-12, live-tested: this previously read
    # os.environ["REVIEWS_TABLE_NAME"], a Lambda environment variable
    # that was never actually set anywhere in Terraform (confirmed via a
    # real KeyError in production) — and even if it had been, it would
    # have deviated from every other Lambda on this same state machine
    # (Audit/Finalize), which all get reviews_table_name/report_bucket
    # injected as a literal ASL Parameter into the event instead, per
    # the "deliberately not caller-supplied input" convention documented
    # where those Parameters are set. Matches that convention now.
    table_name = event["reviews_table_name"]
    client = DynamoDBClient(table_name=table_name)

    existing = client.get_item({"reviewId": review_id}) or {"reviewId": review_id}
    existing.update(
        {
            "status": "needs_clarification",
            # currentStage mirrors status here (2026-10-13 stage-tracker
            # feature) — this Lambda already writes directly to DynamoDB,
            # unlike Ingest/RuleEngine/Validate/Audit/Finalize, which get
            # a currentStage write from a preceding RecordStage* ASL
            # state instead (see infra/modules/step-functions-lambda).
            "currentStage": "needs_clarification",
            "clarificationTaskToken": task_token,
            "needsClarification": event.get("needs_clarification", []),
            "preflightFields": event.get("preflight_fields", {}),
        }
    )
    client.put_item(existing)

    return {"reviewId": review_id, "status": "needs_clarification"}
