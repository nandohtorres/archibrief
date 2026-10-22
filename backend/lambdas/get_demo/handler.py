"""ArchiBrief Lambda: get_demo.

Backs `GET /demo`, the one fully public, unauthenticated route (ADR-0029,
ADR-0044). It serves a precomputed reference report, never a fresh
pipeline run: an unauthenticated endpoint that started a Bedrock-backed
execution per visitor would be a billing and DoS vector with no admin
gate. The handler makes no AWS calls; it returns one JSON file bundled in
its own deployment package.

`reference_report.json` is ported from the frontend's `fixtureReport`
(frontend/lib/fixtures.ts). It is explicitly illustrative (the citations'
`exact_text_span` values say so), not the output of a real
corpus-grounded run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.shared.http import JSON_HEADERS, api_handler

_REFERENCE_REPORT_PATH = Path(__file__).parent / "reference_report.json"
# Read once at import time, so a warm Lambda re-reads nothing per invocation.
_REFERENCE_REPORT = json.loads(_REFERENCE_REPORT_PATH.read_text(encoding="utf-8"))


@api_handler
def handler(_event: dict, _context: object) -> dict[str, Any]:
    return {
        "statusCode": 200,
        "headers": dict(JSON_HEADERS),
        "body": json.dumps(_REFERENCE_REPORT),
    }
