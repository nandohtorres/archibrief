"""ArchiBrief Lambda: create_upload.

Backs `POST /uploads` — the first half of the direct-upload path chosen
for `archive_path` (ADR-0045, drafted 2026-10-12): the client uploads
its own Terraform archive straight to S3 via a presigned POST, instead
of ArchiBrief fetching it from a client-supplied URL server-side. See
that ADR for the full reasoning (GitHub-fetch deferred as a documented
future option, not built here).

Request body: `{"review_id": "..."}` — the same client-generated UUID
the client will later send as `SubmitReviewRequest.review_id`
(frontend/lib/contracts.ts), so the resulting S3 key can be tied to
that review before the review itself exists anywhere server-side.
`review_id` is validated against a conservative safe-character pattern
before being interpolated into the S3 key — it is client-supplied and
otherwise unvalidated at this point in the pipeline, so treating it as
untrusted input here (not just at Ingest, later) avoids a path-
traversal/key-injection shaped bug the same way extract_archive already
treats archive *contents* as untrusted (ADR-0038).

Response: `{"archiveKey": "...", "uploadUrl": "...", "uploadFields": {...}}`
— the frontend POSTs the file directly to `uploadUrl` with
`uploadFields` as additional form fields (the standard S3 presigned-POST
browser upload pattern), never routing the file bytes through this
Lambda or through API Gateway at all.
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

# Generous for Terraform source (which is plain text, typically small)
# without being unbounded — a first-pass ceiling, not calibrated against
# real submission sizes, same caveat as every other first-pass heuristic
# in this codebase (see backend/lambdas/finalize/handler.py's
# compute_cost_estimate_tier).
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
