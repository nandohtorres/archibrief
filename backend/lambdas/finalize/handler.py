"""ArchiBrief Lambda: finalize.

Assembles the structured HTML/JSON evidence ledger from validated
findings and writes pointers to DynamoDB + payload to S3 (400 KB item
cap — ADR-0034). The S3/DynamoDB writes go through the shared client
adapters and cannot succeed without deployed resources, but the ledger
assembly logic itself is real and independently testable.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from backend.shared.clients import DynamoDBClient, S3Client
from backend.shared.models.finding import Finding

MAX_DYNAMODB_ITEM_BYTES = 400 * 1024


def assemble_evidence_ledger(review_id: str, findings: list[Finding]) -> dict[str, Any]:
    by_category: dict[str, list[dict]] = {}
    for f in findings:
        by_category.setdefault(f.category.value, []).append(f.model_dump(mode="json"))

    return {
        "review_id": review_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "finding_count": len(findings),
        "findings_by_category": by_category,
        "findings": [f.model_dump(mode="json") for f in findings],
    }


def handler(event, context):
    review_id = event["review_id"]
    findings = [Finding.model_validate(f) for f in event["findings"]]
    ledger = assemble_evidence_ledger(review_id, findings)

    report_bucket = event.get("report_bucket")
    reviews_table = event.get("reviews_table_name")

    payload_key = f"reports/{review_id}/evidence-ledger.json"
    if report_bucket:
        S3Client(bucket=report_bucket).put_object(
            key=payload_key, body=json.dumps(ledger).encode("utf-8")
        )

    pointer_item = {
        "reviewId": review_id,
        "status": "complete",
        "reportS3Key": payload_key,
        "findingCount": ledger["finding_count"],
        "completedAt": ledger["generated_at"],
    }
    if len(json.dumps(pointer_item).encode("utf-8")) > MAX_DYNAMODB_ITEM_BYTES:
        raise ValueError("review pointer item exceeds DynamoDB 400 KB item cap")

    if reviews_table:
        DynamoDBClient(table_name=reviews_table).put_item(pointer_item)

    return {
        "status": "complete",
        "report_s3_key": payload_key,
        "finding_count": ledger["finding_count"],
    }
