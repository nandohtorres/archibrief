"""ArchiBrief Lambda: create_upload.

Backs `POST /uploads`, the first half of the direct-upload path
(ADR-0045): the client uploads its Terraform archive straight to S3 via a
presigned POST, instead of ArchiBrief fetching it server-side from a
client-supplied URL.

Request body: `{"review_id": "..."}`, the same client-generated ID the
client later sends as `SubmitReviewRequest.review_id`
(frontend/lib/contracts.ts), so the S3 key is tied to the review before
the review exists server-side. `review_id` is untrusted input here, so it
is checked against a conservative safe-character pattern before being
interpolated into the S3 key, preventing path traversal or key injection
(ADR-0038 treats archive contents the same way).

Response: `{"archiveKey": "...", "uploadUrl": "...", "uploadFields": {...}}`.
The frontend POSTs the file to `uploadUrl` with `uploadFields` as form
fields (the standard S3 presigned-POST browser upload), so file bytes
never pass through this Lambda or API Gateway.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from backend.shared.clients import S3Client

# UUID-shaped (crypto.randomUUID()) or the fallback format
# makeIdempotencyKey() uses when crypto.randomUUID is unavailable
# (frontend/lib/workflow.ts: "review-<timestamp>-<hex>") — generous
# enough to cover both without accepting path separators or traversal
# sequences that could escape the "uploads/" key prefix.
_REVIEW_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

# Generous for Terraform source (plain text, typically small) without
# being unbounded. Not yet calibrated against real submission sizes.
_MAX_ARCHIVE_BYTES = 20 * 1024 * 1024


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def handler(event: dict, _context: object) -> dict:
    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "request body must be valid JSON"})

    review_id = payload.get("review_id")
    if not isinstance(review_id, str) or not _REVIEW_ID_PATTERN.match(review_id):
        return _response(400, {"error": "a valid review_id is required"})

    bucket = os.environ["REPORTS_BUCKET_NAME"]
    archive_key = f"uploads/{review_id}/archive.tar"

    presigned = S3Client(bucket=bucket).generate_presigned_post(
        key=archive_key, max_bytes=_MAX_ARCHIVE_BYTES
    )

    return _response(
        200,
        {
            "archiveKey": archive_key,
            "uploadUrl": presigned["url"],
            "uploadFields": presigned["fields"],
        },
    )
