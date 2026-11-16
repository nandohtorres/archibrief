"""Bedrock strict tool schemas reject these keywords: CountTokens fails with
ValidationException and the verifier never runs (live P3b round, 2026-11-16)."""

import json

from backend.shared.finding_verification import VERDICT_SCHEMA

UNSUPPORTED = ("maxItems", "minLength", "maxLength", "pattern", "minimum", "maximum")


def test_verdict_schema_uses_only_bedrock_strict_keywords() -> None:
    text = json.dumps(VERDICT_SCHEMA)
    assert [k for k in UNSUPPORTED if f'"{k}"' in text] == []
