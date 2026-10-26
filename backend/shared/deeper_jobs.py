"""Identifier and public status contract for deeper jobs; no SDK dependencies."""

from __future__ import annotations

import hashlib
import json
import time

JOB_LIFETIME_SECONDS = 420


def job_id_for(review_id: str, finding_id: str) -> str:
    return hashlib.sha256(json.dumps([review_id, finding_id]).encode()).hexdigest()[:32]


def job_key(review_id: str, finding_id: str) -> dict:
    return {"reviewId": review_id, "findingId": f"JOB#{finding_id}"}


def public_job(item: dict, now: int | None = None) -> dict:
    now = int(time.time()) if now is None else now
    status = item["status"]
    expired = status in {"pending", "running"} and int(item["deadline"]) <= now
    return {
        "job_id": item["job_id"],
        "parent_finding_id": item["parent_finding_id"],
        "status": "failed" if expired else status,
        "deadline": int(item["deadline"]),
        "failure_code": "timed_out" if expired else item.get("failure_code"),
    }
