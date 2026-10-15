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
from typing import Any

from backend.lambdas.validate.handler import validate_findings
from backend.shared.clients import AgentCoreRuntimeClient, DynamoDBClient, S3Client
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


def handler(event: dict, _context: object) -> dict:
    path_params = event.get("pathParameters") or {}
    review_id = path_params.get("reviewId")
    finding_id = path_params.get("findingId")
    if not review_id or not finding_id:
        return _response(400, {"error": "reviewId and findingId path parameters are required"})

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

    agent_client = AgentCoreRuntimeClient(agent_runtime_arn=os.environ["AGENTCORE_RUNTIME_ARN"])
    # Fixed-literal prefix guarantees the >=33-char floor AWS enforces on
    # runtimeSessionId regardless of how short review_id/finding_id are —
    # same reasoning as the outer state machine's own RuntimeSessionId
    # (infra/modules/step-functions-lambda's InvokeAgent state), confirmed
    # directly against the real botocore service model while building
    # AgentCoreRuntimeClient's test (not just "commonly cited" anymore).
    runtime_session_id = f"archibrief-deeper-review-session-{review_id}-{finding_id}"
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

    raw_new_findings = agent_response.get("findings", [])
    valid_findings, rejected = validate_findings(raw_new_findings)
    if not valid_findings:
        return _response(
            502,
            {"error": "the deeper evaluation produced no valid findings", "rejected": rejected},
        )

    findings_table = DynamoDBClient(table_name=os.environ["FINDINGS_TABLE_NAME"])
    for finding in valid_findings:
        findings_table.put_item(finding.model_dump(mode="json"))

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
                for f in valid_findings
            ],
        },
    )
