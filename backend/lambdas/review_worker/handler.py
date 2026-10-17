"""Orchestrate content-bearing calls outside durable Step Functions history.

Only review IDs, a server-issued resume reference and a status leave this
handler. Submission/context objects live under jobs/<review ID>/ in S3. No
workflow retry is configured for ambiguous paid calls; claims prevent repeats.
"""

from __future__ import annotations

import json
import os
import re
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from backend.shared.admission import request_digest
from backend.shared.clients import AgentCoreRuntimeClient, DynamoDBClient, S3Client
from backend.shared.kill_switch import paid_work_allowed
from backend.shared.retention import review_is_live


def _invoke(stage: str, payload: dict) -> dict:
    response = boto3.client(
        "lambda",
        config=Config(connect_timeout=2, read_timeout=100, retries={"total_max_attempts": 1}),
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


def _progress(table: DynamoDBClient, review_id: str, stage: str) -> None:
    table.update_item(
        Key={"reviewId": review_id},
        UpdateExpression="SET currentStage = :stage",
        ConditionExpression="attribute_exists(reviewId)",
        ExpressionAttributeValues={":stage": stage},
    )


def _fail(table: DynamoDBClient, review_id: str, code: str) -> dict:
    table.update_item(
        Key={"reviewId": review_id},
        UpdateExpression="SET #s = :failed, failureCode = :code",
        ConditionExpression="attribute_exists(reviewId) AND #s <> :complete",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":failed": "failed", ":code": code, ":complete": "complete"},
    )
    return {"status": "failed"}


def handler(event: dict, _context: object) -> dict:
    # API admission always constructs this envelope, never forwards the body.
    if set(event) - {"review_id", "phase", "resume_key"}:
        raise ValueError("invalid workflow envelope")
    review_id = str(uuid.UUID(event["review_id"]))
    phase = event.get("phase", "initial")
    if phase not in {"initial", "resume", "poll"}:
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
            if review.get("status") in {"complete", "failed", "needs_clarification"}
            else "in_progress"
        }
    bucket = os.environ["REPORTS_BUCKET_NAME"]
    s3 = S3Client(bucket=bucket)
    context_key = f"jobs/{review_id}/context.json"
    try:
        if not paid_work_allowed():
            return _fail(table, review_id, "paused")
        resume_key = event.get("resume_key", "")
        if phase == "initial":
            if review.get("inputKey") != f"jobs/{review_id}/submission.json":
                return _fail(table, review_id, "invalid_submission")
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
                return _fail(table, review_id, "invalid_submission")
            _progress(table, review_id, "ingest")
            ingest = _invoke("ingest", {**submission, "report_bucket": bucket})
            if ingest.get("status") == "rejected":
                return _fail(table, review_id, "invalid_archive")
            if ingest.get("status") == "blocked":
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
            _progress(table, review_id, "rule_engine")
            rules = _invoke(
                "rule_engine",
                {
                    "review_id": review_id,
                    "parsed_s3_key": ingest["parsed_s3_key"],
                    "report_bucket": bucket,
                    "scanner": scanner,
                },
            )
            state = {
                "submission": submission,
                "ingest": ingest,
                "rules": rules,
                "rounds": 0,
                "workload_brief": submission["workload_brief"],
                "baseline_answers": submission["baseline_answers"],
            }
        else:
            if not re.fullmatch(
                rf"jobs/{re.escape(review_id)}/clarification-[a-f0-9]{{64}}\.json", resume_key
            ):
                return _fail(table, review_id, "invalid_submission")
            table.update_item(
                Key={"reviewId": review_id},
                UpdateExpression="SET pipelineResume = :key",
                ConditionExpression="(attribute_not_exists(pipelineResume) OR pipelineResume <> :key) AND #s = :pending",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":key": resume_key, ":pending": "pending"},
            )
            state = _read_json(s3, context_key)
            answer = _read_json(s3, resume_key)
            if answer.get("review_id") != review_id or answer.get("input_digest") != review.get(
                "inputDigest"
            ):
                return _fail(table, review_id, "invalid_submission")
            state["rounds"] += 1
            if state["rounds"] > int(os.environ.get("MAX_CLARIFICATION_ROUNDS", "3")):
                return _fail(table, review_id, "clarification_limit")
            state["baseline_answers"].update(answer["answers"])
            state["workload_brief"] += answer["note"]
        if not review_is_live(table.get_item({"reviewId": review_id}, consistent=True) or {}):
            return {"status": "failed"}
        _progress(table, review_id, "reasoning")
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
            runtime_session_id=f"archibrief-review-session-{review_id}-{state['rounds']}",
        )
        if agent.get("status") == "needs_clarification":
            _write_json(s3, context_key, state)
            table.update_item(
                Key={"reviewId": review_id},
                UpdateExpression="SET needsClarification = :needs, preflightFields = :fields, #s = :waiting",
                ConditionExpression="attribute_exists(reviewId)",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":needs": agent.get("needs_clarification", []),
                    ":fields": agent.get("preflight_fields", {}),
                    ":waiting": "needs_clarification",
                },
            )
            return {"status": "needs_clarification"}
        _progress(table, review_id, "validate")
        validated = _invoke("validate", {"findings": agent["findings"]})
        _progress(table, review_id, "audit")
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
        _progress(table, review_id, "finalize")
        _invoke(
            "finalize",
            {
                "review_id": review_id,
                "findings": validated["valid_findings"],
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
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return {"status": "in_progress"}
        return _fail(table, review_id, "internal_error")
    except Exception as exc:  # noqa: BLE001 - never put stage payloads/errors into workflow history
        print(json.dumps({"event": "review_worker_failed", "kind": type(exc).__name__}))
        return _fail(table, review_id, "internal_error")
