"""Read projection of immutable base evidence plus durable deeper findings.

All report consumers use this assembly after authorization. Invalid children
are excluded with a visible count; storage read failures fail the request.
No mutation of the original S3 ledger is needed.
"""

from __future__ import annotations

import copy
import os
import time
from typing import Any

from pydantic import ValidationError

from backend.shared.analysis_quality import public_analysis_quality
from backend.shared.architecture_links import link_findings
from backend.shared.clients import DynamoDBClient
from backend.shared.deeper_jobs import public_job
from backend.shared.models.finding import Finding
from backend.shared.retention import review_is_live


def assemble_current_ledger(
    ledger: dict[str, Any],
    review_id: str,
    items: list[dict],
    *,
    now: int | None = None,
    children_available: bool = True,
) -> dict[str, Any]:
    current = copy.deepcopy(ledger)
    base = current.get("findings") or []
    known = {f["finding_id"] for f in base}
    parents = set(known)
    accepted = []
    excluded = 0
    runs = {}
    expected_batches = {}
    jobs = []
    now = int(time.time()) if now is None else now
    for item in items:
        if not review_is_live(item, now=now):
            continue
        if item.get("kind") == "deeper-job":
            if item.get("reviewId") == review_id and item.get("parent_finding_id") in parents:
                jobs.append(public_job(item, now))
            continue
        if item.get("kind") == "deeper-result":
            if item.get("reviewId") == review_id and item.get("parent_finding_id") in parents:
                runs[item["parent_finding_id"]] = public_analysis_quality(
                    item.get("analysis_quality")
                )
                ids = item.get("finding_ids")
                if isinstance(ids, list) and all(isinstance(fid, str) for fid in ids):
                    expected_batches[item["parent_finding_id"]] = set(ids)
                else:
                    excluded += 1
            continue
        try:
            finding = Finding.model_validate(item)
        except (ValidationError, TypeError):
            excluded += 1
            continue
        if (
            item.get("reviewId") != review_id
            or finding.review_id != review_id
            or item.get("findingId") != finding.finding_id
            or finding.parent_finding_id not in parents
            or finding.depth_level.value != "deep"
        ):
            excluded += 1
            continue
        if finding.finding_id in known:
            continue
        known.add(finding.finding_id)
        accepted.append(finding.model_dump(mode="json"))
        runs.setdefault(
            finding.parent_finding_id, public_analysis_quality(item.get("analysis_quality"))
        )
    incomplete = {
        parent
        for parent, expected in expected_batches.items()
        if not expected.issubset(
            {
                finding["finding_id"]
                for finding in accepted
                if finding["parent_finding_id"] == parent
            }
        )
    }
    if incomplete:
        removed = [finding for finding in accepted if finding["parent_finding_id"] in incomplete]
        excluded += max(1, len(removed))
        accepted = [
            finding for finding in accepted if finding["parent_finding_id"] not in incomplete
        ]
    current["findings"] = [
        *base,
        *sorted(accepted, key=lambda finding: (finding["created_at"], finding["finding_id"])),
    ]
    current["finding_count"] = len(current["findings"])
    current["findings_by_category"] = {}
    for finding in current["findings"]:
        current["findings_by_category"].setdefault(finding["category"], []).append(finding)
    if accepted and isinstance(current.get("architecture"), dict):
        try:
            current["architecture"] = link_findings(current["architecture"], current["findings"])
        except (KeyError, TypeError, ValueError):
            # A malformed older graph must not hide durable child evidence.
            current.pop("architecture", None)
    current["report_projection"] = {
        "version": 1,
        "children_available": children_available,
        "child_count": len(accepted),
        "excluded_child_count": excluded,
    }
    current["deeper_reviews"] = [
        {"parent_finding_id": parent, "analysis_quality": quality}
        for parent, quality in sorted(runs.items())
    ]
    current["deeper_jobs"] = sorted(jobs, key=lambda job: job["parent_finding_id"])
    return current


def current_ledger(ledger: dict[str, Any], review_id: str) -> dict[str, Any]:
    table = os.environ.get("FINDINGS_TABLE_NAME")
    if not table:
        # Compatibility for an older deployment/configuration is explicit.
        return assemble_current_ledger(ledger, review_id, [], children_available=False)
    items = DynamoDBClient(table_name=table).query_all(
        KeyConditionExpression="reviewId = :rid",
        ExpressionAttributeValues={":rid": review_id},
        ConsistentRead=True,
        Limit=50,
    )
    return assemble_current_ledger(ledger, review_id, items)
