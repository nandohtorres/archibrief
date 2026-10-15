"""ArchiBrief Lambda: deeper_review.

Backs `POST /reviews/{reviewId}/findings/{findingId}/deeper`
(Work-Project-System-Design.md's "API contracts" section) — a scoped
per-finding re-run (Retrieve -> Reason(deep) -> Validate), never the full
pipeline (ADR-0023/ADR-0039). Deliberately bypasses Step Functions
entirely: this is a short, synchronous Lambda-to-AgentCore-to-Lambda call
chain, not a new state machine execution, since nothing here needs
Ingest/RuleEngine/PreflightGate/Audit/Finalize to run again (see
backend/agent/graph.py's build_deeper_graph docstring for the full
reasoning).

Flow:
1. Look up the review's `reportS3Key` from the reviews table (same
   allowlisted-field pattern as get_review.handler).
2. Fetch the evidence ledger JSON from S3 and find the target finding by
   `finding_id` — there's no per-finding DynamoDB row to query directly
   yet (the Findings table exists in Terraform but nothing has ever
   written to it before this handler; see Work-Project-Issues-Log.md,
   2026-10-01 entry), so the ledger is the only source of the original
   finding's content and of `workload_brief` (only ever persisted there,
   per finalize.handler's 2026-10-01 fix — no Reviews-table field carries
   it).
3. Call the deployed AgentCore Runtime directly (AgentCoreRuntimeClient,
   not the Step Functions SDK integration) with `mode: "deeper"`.
4. Validate the returned finding(s) (backend.lambdas.validate's own
   validate_findings, imported in-process — not a second Lambda
   invocation) and write each one to the Findings table, finally
   populating it.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from botocore.exceptions import ClientError, ReadTimeoutError

from backend.lambdas.validate.handler import validate_findings
from backend.shared.clients import AgentCoreRuntimeClient, DynamoDBClient, S3Client
from backend.shared.kill_switch import paid_work_allowed
from backend.shared.models.finding import Finding
from backend.shared.report import compute_presentation


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def _find_parent_finding(ledger: dict[str, Any], finding_id: str) -> dict[str, Any] | None:
    for finding in ledger.get("findings", []):
        if finding.get("finding_id") == finding_id:
            return finding
    return None


def _findings_table_item(finding: Any) -> dict[str, Any]:
    """The Findings table is keyed reviewId (hash) + findingId (range)
    (infra/modules/dynamodb), but Finding serializes snake_case — add the
    table's key attributes or DynamoDB rejects the write."""
    item = finding.model_dump(mode="json")
    return {"reviewId": item["review_id"], "findingId": item["finding_id"], **item}


# Synchronous time budget (Codex F19). HTTP API caps a Lambda integration
# at 30s, so the API integration is set to 29s, the Lambda to 28s, and the
# AgentCore read timeout below both, leaving time to answer cleanly instead
# of the gateway cutting the connection while the Lambda keeps spending.
AGENT_READ_TIMEOUT_SECONDS = 24
# An in-flight claim older than this is treated as abandoned. Longer than
# the Lambda timeout, so a run that timed out still blocks an immediate
# retry from starting a second paid run while the first may still be going.
IN_FLIGHT_STALE_SECONDS = 90


def _in_flight_attribute(finding_id: str) -> str:
    return f"deeperInFlight_{finding_id}"


def _claim_in_flight(client: DynamoDBClient, review_id: str, finding_id: str, now: int) -> bool:
    try:
        client.update_item(
            Key={"reviewId": review_id},
            UpdateExpression="SET #lock = :now",
            ConditionExpression="attribute_exists(reviewId) AND "
            "(attribute_not_exists(#lock) OR #lock < :stale)",
            ExpressionAttributeNames={"#lock": _in_flight_attribute(finding_id)},
            ExpressionAttributeValues={":now": now, ":stale": now - IN_FLIGHT_STALE_SECONDS},
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def _release_in_flight(client: DynamoDBClient, review_id: str, finding_id: str, now: int) -> None:
    # Conditional so a run whose claim went stale and was taken over can't
    # remove the newer run's claim.
    try:
        client.update_item(
            Key={"reviewId": review_id},
            UpdateExpression="REMOVE #lock",
            ConditionExpression="#lock = :now",
            ExpressionAttributeNames={"#lock": _in_flight_attribute(finding_id)},
            ExpressionAttributeValues={":now": now},
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
            raise


def _existing_deeper_findings(
    client: DynamoDBClient, review_id: str, finding_id: str
) -> list[Finding]:
    items = client.query(
        KeyConditionExpression="reviewId = :rid",
        FilterExpression="parent_finding_id = :pid",
        ExpressionAttributeValues={":rid": review_id, ":pid": finding_id},
    )
    return [Finding.model_validate(item) for item in items]


def _findings_response(review_id: str, finding_id: str, findings: list[Finding]) -> dict:
    return _response(
        200,
        {
            "reviewId": review_id,
            "parentFindingId": finding_id,
            # Same {record, presentation} shape build_review_report uses
            # (backend/shared/report.py) — lets the frontend render a
            # returned deeper finding through the exact same ReportFinding
            # components as every other finding, instead of needing its
            # own fabricated priority/label logic.
            "findings": [
                {"record": f.model_dump(mode="json"), "presentation": compute_presentation(f)}
                for f in findings
            ],
        },
    )


def handler(event: dict, _context: object) -> dict:
    path_params = event.get("pathParameters") or {}
    review_id = path_params.get("reviewId")
    finding_id = path_params.get("findingId")
    if not review_id or not finding_id:
        return _response(400, {"error": "reviewId and findingId path parameters are required"})

    if not paid_work_allowed():
        return _response(
            503, {"error": "Deeper analysis is temporarily unavailable. Try again later."}
        )

    reviews_table = DynamoDBClient(table_name=os.environ["REVIEWS_TABLE_NAME"])
    review_item = reviews_table.get_item({"reviewId": review_id})
    if review_item is None:
        return _response(404, {"error": "review not found"})

    report_s3_key = review_item.get("reportS3Key")
    if not report_s3_key:
        return _response(409, {"error": "review has no completed report to go deeper on yet"})

    s3_client = S3Client(bucket=os.environ["REPORTS_BUCKET_NAME"])
    ledger = json.loads(s3_client.get_object(report_s3_key))

    parent_finding = _find_parent_finding(ledger, finding_id)
    if parent_finding is None:
        return _response(404, {"error": "finding not found in this review's report"})

    workload_brief = ledger.get("workload_brief")
    if not workload_brief:
        # A real, known gap for any review finalized before 2026-10-01
        # (finalize.handler only started persisting this then) — not a
        # bug in this handler, flagged rather than silently sending an
        # empty brief to the model.
        return _response(
            409,
            {"error": "this review's original workload brief was not persisted; cannot go deeper"},
        )

    retrieval_query = f"{parent_finding.get('category', '')}: {parent_finding.get('finding', '')}"

    # Idempotency (Codex F19): a finding that was already taken deeper
    # returns its stored result instead of paying for another run, and a
    # per-finding in-flight claim stops a double-click or a client retry
    # after a gateway timeout from starting a second concurrent paid run.
    findings_table = DynamoDBClient(table_name=os.environ["FINDINGS_TABLE_NAME"])
    existing = _existing_deeper_findings(findings_table, review_id, finding_id)
    if existing:
        return _findings_response(review_id, finding_id, existing)

    claimed_at = int(time.time())
    if not _claim_in_flight(reviews_table, review_id, finding_id, claimed_at):
        return _response(
            409,
            {"error": "a deeper analysis for this finding is already running; try again shortly"},
        )

    agent_client = AgentCoreRuntimeClient(
        agent_runtime_arn=os.environ["AGENTCORE_RUNTIME_ARN"],
        read_timeout_seconds=AGENT_READ_TIMEOUT_SECONDS,
    )
    # Fixed-literal prefix guarantees the >=33-char floor AWS enforces on
    # runtimeSessionId regardless of how short review_id/finding_id are —
    # same reasoning as the outer state machine's own RuntimeSessionId
    # (infra/modules/step-functions-lambda's InvokeAgent state), confirmed
    # directly against the real botocore service model while building
    # AgentCoreRuntimeClient's test (not just "commonly cited" anymore).
    runtime_session_id = f"archibrief-deeper-review-session-{review_id}-{finding_id}"
    try:
        agent_response = agent_client.invoke(
            payload={
                "mode": "deeper",
                "review_id": review_id,
                "workload_brief": workload_brief,
                "retrieval_query": retrieval_query,
                "parent_finding_id": finding_id,
                "corpus_version": parent_finding.get("corpus_version", "unknown"),
                "deterministic_rule_version": parent_finding.get("deterministic_rule_version"),
            },
            runtime_session_id=runtime_session_id,
        )
    except ReadTimeoutError:
        # The claim is deliberately left in place: the agent run may still
        # be going, so it only expires after IN_FLIGHT_STALE_SECONDS.
        return _response(
            504,
            {"error": "the deeper analysis took too long; try again in a couple of minutes"},
        )
    except Exception:
        _release_in_flight(reviews_table, review_id, finding_id, claimed_at)
        raise

    raw_new_findings = agent_response.get("findings", [])
    valid_findings, rejected = validate_findings(raw_new_findings)
    if not valid_findings:
        _release_in_flight(reviews_table, review_id, finding_id, claimed_at)
        return _response(
            502,
            {"error": "the deeper evaluation produced no valid findings", "rejected": rejected},
        )

    for finding in valid_findings:
        findings_table.put_item(_findings_table_item(finding))
    _release_in_flight(reviews_table, review_id, finding_id, claimed_at)

    return _findings_response(review_id, finding_id, valid_findings)
