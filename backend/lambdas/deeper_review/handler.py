"""Admit and dispatch a durable deeper job; never call a model from HTTP."""

from __future__ import annotations

import json
import os
import time

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from backend.lambdas.deeper_review.worker import existing_result
from backend.shared.admission import AdmissionDenied, positive_setting, reserve_operation
from backend.shared.clients import DynamoDBClient, S3Client
from backend.shared.deeper_jobs import JOB_LIFETIME_SECONDS, job_id_for, job_key, public_job
from backend.shared.http import JSON_HEADERS, api_handler
from backend.shared.kill_switch import paid_work_allowed
from backend.shared.public_access import capability_allowed
from backend.shared.report import report_findings, stakeholder_view
from backend.shared.retention import review_expires_at, review_is_live


def _response(status_code: int, body: dict) -> dict:
    return {"statusCode": status_code, "headers": dict(JSON_HEADERS), "body": json.dumps(body)}


@api_handler
def handler(event: dict, _context: object) -> dict:
    params = event.get("pathParameters") or {}
    rid, fid = params.get("reviewId"), params.get("findingId")
    if not all(isinstance(value, str) and 0 < len(value) <= 128 for value in (rid, fid)):
        return _response(400, {"error": "invalid_request"})
    review = DynamoDBClient(table_name=os.environ["REVIEWS_TABLE_NAME"]).get_item(
        {"reviewId": rid}, consistent=True
    )
    if (
        not review
        or not review_is_live(review)
        or not capability_allowed(event, review, write=True)
    ):
        return _response(404, {"error": "review not found"})
    if not review.get("reportS3Key"):
        return _response(409, {"error": "review has no completed report"})
    ledger = json.loads(
        S3Client(bucket=os.environ["REPORTS_BUCKET_NAME"]).get_object(review["reportS3Key"])
    )
    if not any(f.get("finding_id") == fid for f in ledger.get("findings", [])):
        return _response(404, {"error": "finding not found"})
    if not ledger.get("workload_brief"):
        return _response(409, {"error": "original workload brief unavailable"})
    table = DynamoDBClient(table_name=os.environ["FINDINGS_TABLE_NAME"])
    findings, quality, complete = existing_result(table, rid, fid)
    if complete:
        if not findings and quality["outcome"] != "no-findings":
            return _response(
                502,
                {
                    "error": "the deeper evaluation produced no valid findings",
                    "analysis_quality": quality,
                },
            )
        return _response(
            200,
            {
                "reviewId": rid,
                "parentFindingId": fid,
                "status": "complete",
                "findings": report_findings(findings, stakeholder_view(findings, ledger)),
                "analysis_quality": quality,
            },
        )
    key = job_key(rid, fid)
    job = table.get_item(key, consistent=True)
    if job and public_job(job)["status"] == "failed":
        return _response(409, {"error": "deeper_job_failed", "job": public_job(job)})
    if not job:
        if not paid_work_allowed():
            return _response(503, {"error": "reviews_paused"})
        try:
            reserve_operation(
                review,
                f"deeper:{fid}",
                {"finding_id": fid},
                positive_setting("DEEPER_RESERVE_MICRO_USD", 200000),
            )
        except AdmissionDenied as exc:
            # An earlier day's claim for this same finding was already paid;
            # the job row was never written (crash between the two writes,
            # or a failed pre-job synchronous attempt). Recover, don't recharge.
            if exc.code != "operation_expired":
                return _response(409 if "operation" in exc.code else 429, {"error": exc.code})
        now = int(time.time())
        job = {
            **key,
            "kind": "deeper-job",
            "job_id": job_id_for(rid, fid),
            "parent_finding_id": fid,
            "status": "pending",
            "queued_at": now,
            "deadline": min(now + JOB_LIFETIME_SECONDS, review_expires_at(review)),
            "ttl": review_expires_at(review),
        }
        try:
            table.put_item(job, ConditionExpression="attribute_not_exists(findingId)")
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            job = table.get_item(key, consistent=True)
    if public_job(job)["status"] == "failed":
        return _response(409, {"error": "deeper_job_failed", "job": public_job(job)})
    if job["status"] == "pending":
        try:
            boto3.client(
                "stepfunctions",
                config=Config(connect_timeout=1, read_timeout=3, retries={"total_max_attempts": 1}),
            ).start_execution(
                stateMachineArn=os.environ["DEEPER_STATE_MACHINE_ARN"],
                name=f"deeper-{job['job_id']}",
                input=json.dumps(
                    {"review_id": rid, "finding_id": fid, "job_id": job["job_id"]}, sort_keys=True
                ),
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ExecutionAlreadyExists":
                return _response(
                    503, {"error": "deeper_dispatch_unavailable", "job": public_job(job)}
                )
        except Exception:  # noqa: BLE001 - same name/input recovers ambiguous dispatch
            return _response(503, {"error": "deeper_dispatch_unavailable", "job": public_job(job)})
    return _response(202, {"reviewId": rid, "status": job["status"], "job": public_job(job)})
