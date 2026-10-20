"""A small stored review (evidence-ledger shape) the chat tests share."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

# The same review the paid trap run uses, so free and paid runs agree.
LEDGER = json.loads(
    (
        Path(__file__).resolve().parents[3]
        / "backend"
        / "chat"
        / "eval_fixture_ledger.json"
    ).read_text(encoding="utf-8")
)
CHUNK_TEXT = LEDGER["findings"][2]["citation"]["exact_text_span"]

RULE_FINDING_ID = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def ledger() -> dict:
    return copy.deepcopy(LEDGER)
