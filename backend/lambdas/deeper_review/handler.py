"""ArchiBrief Lambda: deeper_review.

Backs `POST /reviews/{reviewId}/findings/{findingId}/deeper`: a scoped
per-finding re-run (Retrieve -> Reason(deep) -> Validate), never the full
pipeline (ADR-0023/ADR-0039). It bypasses Step Functions: nothing here
needs Ingest/RuleEngine/PreflightGate/Audit/Finalize to run again, so it
is a short synchronous call to AgentCore rather than a new execution (see
build_deeper_graph in backend/agent/graph.py).

Flow:
1. Look up the review's `reportS3Key` in the reviews table.
2. Fetch the evidence ledger from S3 and find the target finding by
   `finding_id`. The ledger is the only source of the original finding
   and of `workload_brief`.
3. Call the AgentCore Runtime directly (AgentCoreRuntimeClient) with
   `mode: "deeper"`.
4. Validate the returned findings in-process (validate_findings from
   backend.lambdas.validate) and write each one to the Findings table.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from botocore.exceptions import ClientError, ReadTimeoutError

from backend.lambdas.validate.handler import validate_findings
from backend.shared.admission import AdmissionDenied, positive_setting, reserve_operation
from backend.shared.analysis_quality import build_analysis_quality, public_analysis_quality
from backend.shared.clients import (
    AgentCoreRuntimeClient,
    DynamoDBClient,
    DynamoDBTransactionClient,
    S3Client,
    TransactionCanceled,
)
from backend.shared.http import JSON_HEADERS, api_handler
from backend.shared.kill_switch import paid_work_allowed
from backend.shared.models.finding import DepthLevel, Finding
from backend.shared.public_access import capability_allowed
from backend.shared.report import report_findings, stakeholder_view
from backend.shared.retention import review_expires_at, review_is_live


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": dict(JSON_HEADERS),
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


# Synchronous time budget. HTTP API caps a Lambda integration
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
) -> tuple[list[Finding], dict, bool]:
    items = client.query_all(
        KeyConditionExpression="reviewId = :rid",
        FilterExpression="parent_finding_id = :pid",
        ExpressionAttributeValues={":rid": review_id, ":pid": finding_id},
        ConsistentRead=True,
        Limit=50,
    )
    items = [item for item in items if review_is_live(item)]
    marker = next((item for item in items if item.get("kind") == "deeper-result"), None)
    records = [item for item in items if item.get("kind") != "deeper-result"]
    if marker:
        expected = set(marker["finding_ids"])
        records = [item for item in records if item.get("finding_id") in expected]
        if {item.get("finding_id") for item in records} != expected:
            raise ValueError("incomplete stored deeper result")
    return (
        [Finding.model_validate(item) for item in records],
        public_analysis_quality(
            (marker or (records[0] if records else {})).get("analysis_quality")
        ),
        marker is not None or bool(records),
    )


def _findings_response(
    review_id: str, finding_id: str, findings: list[Finding], quality: dict | None = None
) -> dict:
    if not findings and public_analysis_quality(quality)["outcome"] != "no-findings":
        return _response(
            502,
            {
                "error": "the deeper evaluation produced no valid findings",
                "analysis_quality": public_analysis_quality(quality),
            },
        )
    return _response(
        200,
        {
            "reviewId": review_id,
            "parentFindingId": finding_id,
            # Same {record, presentation} shape build_review_report uses
            # (backend/shared/report.py), so the frontend renders a deeper
            # finding with the same components as every other finding.
            "findings": report_findings(findings, stakeholder_view(findings, {})),
            "analysis_quality": public_analysis_quality(quality),
        },
    )


@api_handler
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
    if (
        review_item is None
        or not review_is_live(review_item)
        or not capability_allowed(event, review_item, write=True)
    ):
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
        # Older ledgers may lack the brief; refuse rather than send the
        # model an empty one.
        return _response(
            409,
            {"error": "this review's original workload brief was not persisted; cannot go deeper"},
        )

    retrieval_query = f"{parent_finding.get('category', '')}: {parent_finding.get('finding', '')}"

    # Idempotency: a finding that was already taken deeper
    # returns its stored result instead of paying for another run, and a
    # per-finding in-flight claim stops a double-click or a client retry
    # after a gateway timeout from starting a second concurrent paid run.
    findings_table = DynamoDBClient(table_name=os.environ["FINDINGS_TABLE_NAME"])
    existing, existing_quality, completed = _existing_deeper_findings(
        findings_table, review_id, finding_id
    )
    if completed:
        return _findings_response(review_id, finding_id, existing, existing_quality)

    claimed_at = int(time.time())
    if not _claim_in_flight(reviews_table, review_id, finding_id, claimed_at):
        return _response(
            409,
            {"error": "a deeper analysis for this finding is already running; try again shortly"},
        )
    # Another run may have committed between the first read and our claim.
    existing, existing_quality, completed = _existing_deeper_findings(
        findings_table, review_id, finding_id
    )
    if completed:
        _release_in_flight(reviews_table, review_id, finding_id, claimed_at)
        return _findings_response(review_id, finding_id, existing, existing_quality)

    try:
        fresh = reserve_operation(
            review_item,
            f"deeper:{finding_id}:{claimed_at}",
            {"finding_id": finding_id},
            positive_setting("DEEPER_RESERVE_MICRO_USD", 200000),
        )
        if not fresh:
            raise AdmissionDenied("operation_in_progress")
    except AdmissionDenied as exc:
        _release_in_flight(reviews_table, review_id, finding_id, claimed_at)
        return _response(409 if "operation" in exc.code else 429, {"error": exc.code})

    agent_client = AgentCoreRuntimeClient(
        agent_runtime_arn=os.environ["AGENTCORE_RUNTIME_ARN"],
        read_timeout_seconds=AGENT_READ_TIMEOUT_SECONDS,
    )
    # The fixed prefix guarantees the 33-character minimum AWS enforces on
    # runtimeSessionId however short review_id/finding_id are (the state
    # machine's InvokeAgent state does the same).
    runtime_session_id = f"archibrief-deeper-review-session-{review_id}-{finding_id}"
    try:
        agent_response = agent_client.invoke(
            payload={
                "mode": "deeper",
                "review_id": review_id,
                "workload_brief": workload_brief,
                "retrieval_query": retrieval_query,
                "parent_finding_id": finding_id,
                "parent_finding": parent_finding,
                "terraform_resources": ledger.get("terraform_resources") or {},
                "preflight_fields": {
                    answer["field"]: {
                        "value": answer.get("value"),
                        "outcome": answer.get("outcome"),
                        "is_assumption": answer.get("outcome") == "assumption",
                    }
                    for answer in ledger.get("baseline_answers") or []
                    if isinstance(answer, dict) and isinstance(answer.get("field"), str)
                },
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
    valid_findings, _rejected = validate_findings(raw_new_findings)
    quality = build_analysis_quality(
        agent_response.get("model_output_counts"),
        raw_new_findings,
        [finding.model_dump(mode="json") for finding in valid_findings],
    )
    valid_findings = [
        finding.model_copy(
            update={
                "review_id": review_id,
                "parent_finding_id": finding_id,
                "depth_level": DepthLevel.DEEP,
            }
        )
        for finding in valid_findings
    ]
    if len(valid_findings) > 98:
        raise ValueError("deeper result exceeds atomic batch limit")
    deadline = review_expires_at(review_item)
    committed_at = int(time.time())
    if deadline <= committed_at:
        return _response(409, {"error": "review expired before the deeper result could be saved"})
    marker = {
        "reviewId": review_id,
        "findingId": f"RESULT#{finding_id}",
        "kind": "deeper-result",
        "parent_finding_id": finding_id,
        "finding_ids": [finding.finding_id for finding in valid_findings],
        "analysis_quality": quality,
        "ttl": deadline,
    }
    # Every child and its completion marker commit together. The lock check
    # prevents a timed-out/stale attempt from publishing over a newer one.
    actions = [
        {
            "Put": {
                "TableName": os.environ["FINDINGS_TABLE_NAME"],
                "Item": {
                    **_findings_table_item(finding),
                    "ttl": deadline,
                    "analysis_quality": quality,
                },
            }
        }
        for finding in valid_findings
    ]
    actions.extend(
        [
            {"Put": {"TableName": os.environ["FINDINGS_TABLE_NAME"], "Item": marker}},
            {
                "Update": {
                    "TableName": os.environ["REVIEWS_TABLE_NAME"],
                    "Key": {"reviewId": review_id},
                    "UpdateExpression": "REMOVE #lock",
                    "ConditionExpression": "#lock = :claim AND (attribute_not_exists(#ttl) OR #ttl > :now)",
                    "ExpressionAttributeNames": {
                        "#lock": _in_flight_attribute(finding_id),
                        "#ttl": "ttl",
                    },
                    "ExpressionAttributeValues": {":claim": claimed_at, ":now": committed_at},
                }
            },
        ]
    )
    try:
        DynamoDBTransactionClient().transact_write(actions)
    except TransactionCanceled:
        return _response(
            409, {"error": "the deeper result could not be committed; reload the report"}
        )

    return _findings_response(review_id, finding_id, valid_findings, quality)
