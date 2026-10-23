"""Identifier-only durable deeper jobs. No automatic retry of model calls."""

from __future__ import annotations

import json
import os
import time

from botocore.exceptions import ClientError

from backend.lambdas.validate.handler import validate_findings
from backend.shared.analysis_quality import build_analysis_quality, public_analysis_quality
from backend.shared.clients import (
    AgentCoreRuntimeClient,
    DynamoDBClient,
    DynamoDBTransactionClient,
    S3Client,
)
from backend.shared.deeper_jobs import job_id_for, job_key, public_job
from backend.shared.kill_switch import paid_work_allowed
from backend.shared.models.finding import DepthLevel, Finding
from backend.shared.retention import review_expires_at, review_is_live

AGENT_READ_TIMEOUT_SECONDS = 300


def existing_result(
    table: DynamoDBClient, review_id: str, finding_id: str
) -> tuple[list[Finding], dict, bool]:
    items = table.query_all(
        KeyConditionExpression="reviewId = :rid",
        FilterExpression="parent_finding_id = :pid",
        ExpressionAttributeValues={":rid": review_id, ":pid": finding_id},
        ConsistentRead=True,
        Limit=50,
    )
    items = [item for item in items if review_is_live(item) and item.get("kind") != "deeper-job"]
    marker = next((item for item in items if item.get("kind") == "deeper-result"), None)
    records = [item for item in items if item.get("kind") != "deeper-result"]
    if marker:
        expected = set(marker["finding_ids"])
        records = [item for item in records if item.get("finding_id") in expected]
        if {item.get("finding_id") for item in records} != expected:
            raise ValueError("incomplete stored deeper result")
    findings = [Finding.model_validate(item) for item in records]
    if any(f.review_id != review_id or f.parent_finding_id != finding_id for f in findings):
        raise ValueError("invalid stored deeper context")
    return (
        findings,
        public_analysis_quality(
            (marker or (records[0] if records else {})).get("analysis_quality")
        ),
        marker is not None or bool(records),
    )


def _fail(table: DynamoDBClient, review_id: str, finding_id: str, job_id: str, code: str) -> dict:
    try:
        table.update_item(
            Key=job_key(review_id, finding_id),
            UpdateExpression="SET #s = :failed, failure_code = :code",
            ConditionExpression="job_id = :job AND (#s = :pending OR #s = :running)",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":job": job_id,
                ":pending": "pending",
                ":running": "running",
                ":failed": "failed",
                ":code": code,
            },
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
    return {"status": "failed"}


def run_job(event: dict, _context: object) -> dict:
    if set(event) != {"review_id", "finding_id", "job_id", "phase"} or event["phase"] not in {
        "run",
        "fail",
    }:
        raise ValueError("invalid deeper job envelope")
    rid, fid, jid = event["review_id"], event["finding_id"], event["job_id"]
    if not all(
        isinstance(value, str) and 0 < len(value) <= 128 for value in (rid, fid, jid)
    ) or jid != job_id_for(rid, fid):
        raise ValueError("invalid deeper job identity")
    table = DynamoDBClient(table_name=os.environ["FINDINGS_TABLE_NAME"])
    job = table.get_item(job_key(rid, fid), consistent=True)
    if not job or job.get("job_id") != jid:
        return {"status": "failed"}
    if event["phase"] == "fail":
        return _fail(table, rid, fid, jid, "timed_out")
    if job["status"] in {"complete", "failed"}:
        return {"status": job["status"]}
    if public_job(job)["status"] == "failed":
        return _fail(table, rid, fid, jid, "timed_out")
    try:
        table.update_item(
            Key=job_key(rid, fid),
            UpdateExpression="SET #s = :running",
            ConditionExpression="job_id = :job AND #s = :pending AND deadline > :now",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":job": jid,
                ":pending": "pending",
                ":running": "running",
                ":now": int(time.time()),
            },
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return {"status": "in_progress"}
        raise
    try:
        review = DynamoDBClient(table_name=os.environ["REVIEWS_TABLE_NAME"]).get_item(
            {"reviewId": rid}, consistent=True
        )
        if not review or not review_is_live(review) or not paid_work_allowed():
            return _fail(table, rid, fid, jid, "unavailable")
        ledger = json.loads(
            S3Client(bucket=os.environ["REPORTS_BUCKET_NAME"]).get_object(review["reportS3Key"])
        )
        parent = next((f for f in ledger.get("findings", []) if f.get("finding_id") == fid), None)
        if parent is None or not ledger.get("workload_brief"):
            return _fail(table, rid, fid, jid, "invalid_context")
        result = AgentCoreRuntimeClient(
            agent_runtime_arn=os.environ["AGENTCORE_RUNTIME_ARN"],
            read_timeout_seconds=AGENT_READ_TIMEOUT_SECONDS,
        ).invoke(
            payload={
                "mode": "deeper",
                "review_id": rid,
                "parent_finding_id": fid,
                "parent_finding": parent,
                "workload_brief": ledger["workload_brief"],
                "retrieval_query": f"{parent.get('category', '')}: {parent.get('finding', '')}",
                "terraform_resources": ledger.get("terraform_resources") or {},
                "preflight_fields": {
                    a["field"]: {
                        "value": a.get("value"),
                        "outcome": a.get("outcome"),
                        "is_assumption": a.get("outcome") == "assumption",
                    }
                    for a in ledger.get("baseline_answers") or []
                    if isinstance(a, dict) and isinstance(a.get("field"), str)
                },
                "corpus_version": parent.get("corpus_version", "unknown"),
                "deterministic_rule_version": parent.get("deterministic_rule_version"),
            },
            runtime_session_id=f"archibrief-deeper-review-session-{jid}",
        )
        raw = result["findings"]
        valid, _rejected = validate_findings(raw)
        quality = build_analysis_quality(
            result.get("model_output_counts"), raw, [f.model_dump(mode="json") for f in valid]
        )
        findings = [
            f.model_copy(
                update={"review_id": rid, "parent_finding_id": fid, "depth_level": DepthLevel.DEEP}
            )
            for f in valid
        ]
        if (
            len(findings) > 98
            or len({f.finding_id for f in findings}) != len(findings)
            or any(
                f.finding_id in {p["finding_id"] for p in ledger["findings"]}
                or f.finding_id.startswith(("JOB#", "RESULT#"))
                for f in findings
            )
        ):
            return _fail(table, rid, fid, jid, "invalid_output")
        now = int(time.time())
        if min(review_expires_at(review), int(job["deadline"])) <= now:
            return _fail(table, rid, fid, jid, "timed_out")
        ttl = review_expires_at(review)
        rows = [
            {
                "reviewId": rid,
                "findingId": f.finding_id,
                **f.model_dump(mode="json"),
                "ttl": ttl,
                "analysis_quality": quality,
            }
            for f in findings
        ]
        rows.append(
            {
                "reviewId": rid,
                "findingId": f"RESULT#{fid}",
                "kind": "deeper-result",
                "parent_finding_id": fid,
                "finding_ids": [f.finding_id for f in findings],
                "analysis_quality": quality,
                "ttl": ttl,
            }
        )
        actions = [
            {"Put": {"TableName": os.environ["FINDINGS_TABLE_NAME"], "Item": row}} for row in rows
        ]
        actions.append(
            {
                "Update": {
                    "TableName": os.environ["FINDINGS_TABLE_NAME"],
                    "Key": job_key(rid, fid),
                    "UpdateExpression": "SET #s = :complete",
                    "ConditionExpression": "job_id = :job AND #s = :running AND deadline > :now AND #ttl > :now",
                    "ExpressionAttributeNames": {"#s": "status", "#ttl": "ttl"},
                    "ExpressionAttributeValues": {
                        ":job": jid,
                        ":running": "running",
                        ":complete": "complete",
                        ":now": now,
                    },
                }
            }
        )
        DynamoDBTransactionClient().transact_write(actions)
        return {"status": "complete"}
    except Exception as exc:  # noqa: BLE001 - no payloads/errors in durable history
        print(json.dumps({"event": "deeper_job_failed", "kind": type(exc).__name__}))
        return _fail(table, rid, fid, jid, "analysis_failed")
