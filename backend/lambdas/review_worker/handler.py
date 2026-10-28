"""Orchestrate content-bearing calls outside durable Step Functions history.

Only review IDs and a status leave this handler. Submission/context objects live under jobs/<review ID>/ in S3. No
workflow retry is configured for ambiguous paid calls; claims prevent repeats.
"""

from __future__ import annotations

import json
import os
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from backend.shared.admission import release_operation, request_digest
from backend.shared.analysis_quality import build_analysis_quality
from backend.shared.architecture_links import link_findings
from backend.shared.clients import AgentCoreRuntimeClient, DynamoDBClient, S3Client
from backend.shared.kill_switch import paid_work_allowed
from backend.shared.retention import review_is_live


def _invoke(stage: str, payload: dict) -> dict:
    # No stage calls the model, so transient throttling or service errors are
    # retried. Audit is not: each run writes a new row. AgentCore is not either.
    attempts = 1 if stage == "audit" else 3
    response = boto3.client(
        "lambda",
        config=Config(
            connect_timeout=2,
            read_timeout=100,
            retries={"mode": "standard", "total_max_attempts": attempts},
        ),
    ).invoke(
        FunctionName=os.environ[f"{stage.upper()}_FUNCTION_NAME"],
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode(),
    )
    if response.get("FunctionError"):
        raise RuntimeError("review stage failed")
    result = json.loads(response["Payload"].read())
    if not isinstance(result, dict):
        raise TypeError("review stage returned an invalid result")
    return result


def _write_json(s3: S3Client, key: str, payload: dict) -> None:
    s3.put_object(key, json.dumps(payload).encode())


def _read_json(s3: S3Client, key: str) -> dict:
    value = json.loads(s3.get_object(key))
    if not isinstance(value, dict):
        raise TypeError("invalid stored context")
    return value


def _progress(table: DynamoDBClient, review_id: str, stage: str) -> str:
    table.update_item(
        Key={"reviewId": review_id},
        UpdateExpression="SET currentStage = :stage",
        ConditionExpression="attribute_exists(reviewId)",
        ExpressionAttributeValues={":stage": stage},
    )
    return stage


def _save_preview_diagram(
    s3: S3Client, table: DynamoDBClient, review_id: str, graph: object
) -> None:
    """The report's diagram, saved as soon as RuleEngine builds it so the
    progress screen can show it while the model runs. Best effort: a
    failure here only means no preview."""
    if not isinstance(graph, dict):
        return
    key = f"jobs/{review_id}/architecture.json"
    try:
        _write_json(s3, key, link_findings(graph, []))
        table.update_item(
            Key={"reviewId": review_id},
            UpdateExpression="SET previewArchitectureKey = :key",
            ConditionExpression="attribute_exists(reviewId)",
            ExpressionAttributeValues={":key": key},
        )
    except Exception as exc:  # noqa: BLE001 - the review continues without a preview
        print(json.dumps({"event": "preview_diagram_failed", "kind": type(exc).__name__}))


def _fail(table: DynamoDBClient, review_id: str, code: str) -> dict:
    table.update_item(
        Key={"reviewId": review_id},
        UpdateExpression="SET #s = :failed, failureCode = :code",
        ConditionExpression="attribute_exists(reviewId) AND #s <> :complete",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":failed": "failed", ":code": code, ":complete": "complete"},
    )
    return {"status": "failed"}


def _fail_unpaid(table: DynamoDBClient, review_id: str, code: str, operation: str) -> dict:
    """Fail a review before any billed call (model or Guardrails) and give back its reservation."""
    result = _fail(table, review_id, code)
    try:
        release_operation(review_id, operation)
    except Exception:  # noqa: BLE001 - the review is already marked failed
        print(json.dumps({"event": "reservation_release_failed", "operation": operation}))
    return result


def handler(event: dict, _context: object) -> dict:
    # API admission always constructs this envelope, never forwards the body.
    if set(event) - {"review_id", "phase"}:
        raise ValueError("invalid workflow envelope")
    review_id = str(uuid.UUID(event["review_id"]))
    phase = event.get("phase", "initial")
    if phase not in {"initial", "poll"}:
        raise ValueError("invalid workflow phase")
    table = DynamoDBClient(table_name=os.environ["REVIEWS_TABLE_NAME"])
    review = table.get_item({"reviewId": review_id}, consistent=True)
    if not review or not review_is_live(review):
        return {"status": "failed"}
    if review.get("status") == "complete":
        return {"status": "complete"}
    if phase == "poll":
        return {
            "status": review["status"]
            if review.get("status") in {"complete", "failed"}
            else "in_progress"
        }
    bucket = os.environ["REPORTS_BUCKET_NAME"]
    s3 = S3Client(bucket=bucket)
    # The claim submit_review reserved for this run.
    operation = "initial"
    stage = "admission"
    try:
        if not paid_work_allowed():
            return _fail_unpaid(table, review_id, "paused", operation)
        if review.get("inputKey") != f"jobs/{review_id}/submission.json":
            return _fail_unpaid(table, review_id, "invalid_submission", operation)
        table.update_item(
            Key={"reviewId": review_id},
            UpdateExpression="SET pipelineStarted = :yes",
            ConditionExpression="attribute_not_exists(pipelineStarted) AND inputDigest = :digest AND #s = :pending",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":yes": True,
                ":digest": review["inputDigest"],
                ":pending": "pending",
            },
        )
        submission = _read_json(s3, review["inputKey"])
        if request_digest(submission) != review["inputDigest"]:
            return _fail_unpaid(table, review_id, "invalid_submission", operation)
        stage = _progress(table, review_id, "ingest")
        ingest = _invoke("ingest", {**submission, "report_bucket": bucket})
        if ingest.get("status") == "rejected":
            return _fail_unpaid(table, review_id, "invalid_archive", operation)
        if ingest.get("status") == "blocked":
            # Guardrails, which is billed, has already run.
            return _fail(table, review_id, "input_blocked")
        if ingest.get("status") != "parsed":
            return _fail(table, review_id, "internal_error")
        scanner = _invoke(
            "scan",
            {
                "review_id": review_id,
                "archive_s3_key": submission["archive_s3_key"],
                "archive_s3_version": submission["archive_s3_version"],
                "report_bucket": bucket,
            },
        )
        stage = _progress(table, review_id, "rule_engine")
        rules = _invoke(
            "rule_engine",
            {
                "review_id": review_id,
                "parsed_s3_key": ingest["parsed_s3_key"],
                "report_bucket": bucket,
                "scanner": scanner,
            },
        )
        _save_preview_diagram(s3, table, review_id, rules.get("architecture"))
        state = {
            "submission": submission,
            "ingest": ingest,
            "rules": rules,
            "workload_brief": submission["workload_brief"],
            "baseline_answers": submission["baseline_answers"],
        }
        if not review_is_live(table.get_item({"reviewId": review_id}, consistent=True) or {}):
            return {"status": "failed"}
        stage = _progress(table, review_id, "reasoning")
        rules = state["rules"]
        agent = AgentCoreRuntimeClient(
            agent_runtime_arn=os.environ["AGENTCORE_RUNTIME_ARN"], read_timeout_seconds=300
        ).invoke(
            payload={
                "review_id": review_id,
                "workload_brief": state["workload_brief"],
                "baseline_answers": state["baseline_answers"],
                "retrieval_query": state["submission"]["retrieval_query"],
                "rule_findings": rules["findings"],
                "deterministic_rule_version": rules["rule_version"],
                "terraform_resources": rules.get("resource_summary", {}),
            },
            runtime_session_id=f"archibrief-review-session-{review_id}-0",
        )
        if agent.get("status") == "needs_clarification":
            # No field pauses any more (submit_review requires the
            # regulatory answer), so this would be a preflight policy bug.
            return _fail(table, review_id, "internal_error")
        stage = _progress(table, review_id, "validate")
        validated = _invoke("validate", {"findings": agent["findings"]})
        quality = build_analysis_quality(
            agent.get("model_output_counts"), agent["findings"], validated["valid_findings"]
        )
        stage = _progress(table, review_id, "audit")
        _invoke(
            "audit",
            {
                "review_id": review_id,
                "review_created_at": review["createdAt"],
                "baseline_answers": state["baseline_answers"],
                "guardrails_decisions": state["ingest"].get("guardrails_decisions", []),
                "deterministic_rule_version": rules["rule_version"],
            },
        )
        stage = _progress(table, review_id, "finalize")
        _invoke(
            "finalize",
            {
                "review_id": review_id,
                "findings": validated["valid_findings"],
                "analysis_quality": quality,
                "workload_brief": state["workload_brief"],
                "preflight_fields": agent.get("preflight_fields", {}),
                "defaults_version": agent.get("defaults_version"),
                "resource_count": state["ingest"].get("resource_count", 0),
                "terraform_resources": rules.get("resource_summary", {}),
                "architecture": rules.get("architecture"),
                "report_bucket": bucket,
                "reviews_table_name": os.environ["REVIEWS_TABLE_NAME"],
            },
        )
        return {"status": "complete"}
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code == "ConditionalCheckFailedException":
            return {"status": "in_progress"}
        # Error type and code only: a stage's message can echo its payload.
        print(
            json.dumps(
                {
                    "event": "review_worker_failed",
                    "stage": stage,
                    "kind": type(exc).__name__,
                    "code": code,
                }
            )
        )
        return _fail(table, review_id, "internal_error")
    except Exception as exc:  # noqa: BLE001 - never put stage payloads/errors into workflow history
        print(
            json.dumps(
                {"event": "review_worker_failed", "stage": stage, "kind": type(exc).__name__}
            )
        )
        return _fail(table, review_id, "internal_error")
