"""ArchiBrief Lambda: get_demo.

Backs `GET /demo` — the one fully public, unauthenticated route (ADR-0029,
ADR-0044, Work-Project-System-Design.md's "API contracts" section).
Serves a **precomputed/cached** reference report, never a fresh pipeline
run per visitor: ADR-0029's own reasoning is cost/abuse exposure — an
unauthenticated endpoint that triggered a real Bedrock-backed execution
per visitor would be a billing and DoS vector with no admin gate to stop
it. This handler makes zero AWS calls and touches none of the real
pipeline's resources (DynamoDB, S3, Step Functions, AgentCore) — it reads
one bundled JSON file shipped in its own deployment package and returns
it verbatim.

`reference_report.json` is ported from the frontend's own
`fixtureReport` (frontend/lib/fixtures.ts) — the same illustrative
reference scenario Codex and the frontend work already settled on,
rather than inventing new demo content. It is explicitly illustrative
(citations' `exact_text_span` say so) — generating a genuinely
corpus-grounded demo report would require a real Bedrock-backed run,
which is out of scope here (no live AWS calls without Fernando's
go-ahead) and is tracked as a follow-up, not silently implied to be done.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_REFERENCE_REPORT_PATH = Path(__file__).parent / "reference_report.json"
# Read once at import time (module-level singleton, same reasoning as
# runtime_entrypoint.py's module-level clients) — a warm Lambda process
# re-reads nothing per invocation; this file never changes at runtime.
_REFERENCE_REPORT = json.loads(_REFERENCE_REPORT_PATH.read_text(encoding="utf-8"))


def handler(_event: dict, _context: object) -> dict[str, Any]:
    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(_REFERENCE_REPORT),
    }
