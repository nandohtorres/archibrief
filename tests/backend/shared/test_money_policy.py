"""The backend's no-monetary-estimates policy, checked against the cases the
frontend's implementation also must pass (tests/shared/money-policy-cases.json)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.shared.money_policy import (
    code_without_money,
    field_without_money,
    narrative_without_money,
    public_answer,
)

CASES = json.loads(
    (
        Path(__file__).resolve().parents[2] / "shared" / "money-policy-cases.json"
    ).read_text(encoding="utf-8")
)["cases"]
MODES = {
    "field": field_without_money,
    "narrative": narrative_without_money,
    "code": code_without_money,
}


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_shared_conformance_case(case):
    text, removed = MODES[case["mode"]](case["input"])
    assert text == case["expected"]
    assert removed == case["removed"]


def test_public_answer_omits_a_priced_quote_and_counts_removals():
    paragraphs = [
        {
            "text": "A standby helps. It costs about $150 a month.",
            "citations": [
                {
                    "kind": "source",
                    "quote": "Multi-AZ is billed at $0.342 per hour.",
                    "source_url": "u",
                },
                {"kind": "finding", "finding_id": "f1", "title": "t"},
            ],
        },
        {
            "text": "Test a failover.",
            "citations": [
                {"kind": "source", "quote": "Test failover.", "source_url": "u"}
            ],
        },
    ]
    public, removed, omitted = public_answer(paragraphs)
    assert public[0]["text"] == "A standby helps."
    assert public[0]["amounts_removed"] == 1
    assert public[0]["citations"][0]["quote"] == ""
    assert public[0]["citations"][0]["quote_omitted"] == "monetary-amount"
    assert public[0]["citations"][0]["source_url"] == "u"
    assert public[0]["citations"][1] == paragraphs[0]["citations"][1]
    assert public[1] == paragraphs[1]
    assert (removed, omitted) == (1, 1)
    # The stored answer is not changed.
    assert paragraphs[0]["text"].endswith("$150 a month.")
    assert paragraphs[0]["citations"][0]["quote"].startswith("Multi-AZ")
