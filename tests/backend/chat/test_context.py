"""What the chat model is told about a review (ADR-0050 §3)."""

from __future__ import annotations

import json

from backend.chat.context import (
    NO_RESOURCES_NOTE,
    PRIORITY_BY_TYPE,
    REVIEW_BLOCK_CHARS,
    build_review_context,
)
from backend.shared.models.finding import FindingType
from backend.shared.report import _PRIORITY_BY_TYPE
from tests.backend.chat.conftest import RULE_FINDING_ID


def test_priority_buckets_match_the_report():
    assert PRIORITY_BY_TYPE == {t.value: p for t, (p, _) in _PRIORITY_BY_TYPE.items()}
    assert set(PRIORITY_BY_TYPE) == {t.value for t in FindingType}


def test_findings_are_aliased_most_important_first(ledger):
    ctx = build_review_context(ledger)
    assert ctx.finding_ids["F1"] == RULE_FINDING_ID  # high risk first
    assert [f["priority"] for f in ctx.review_data["findings"]] == [
        "high",
        "review",
        "unknown",
        "confirmed",
    ]
    assert ctx.not_observable_aliases == ["F3"]
    assert ctx.alternatives == [("F1", "AWS managed ReadOnlyAccess")]
    assert "C-F2" in ctx.finding_citations
    assert ctx.resource_addresses == {
        "aws_s3_bucket_public_access_block.audit",
        "aws_lambda_function.api",
    }
    assert set(ctx.requirement_labels) == {
        "expected_traffic_scale",
        "availability_criticality",
    }


def test_the_model_never_sees_finding_uuids_or_internal_fields(ledger):
    text = build_review_context(ledger).cached_text()
    for finding in ledger["findings"]:
        assert finding["finding_id"] not in text
    for internal in ("retrieved_chunk_ids", "model_id", "prompt_version", "created_at"):
        assert internal not in text


def test_report_text_is_normalized_and_clipped(ledger):
    ledger["findings"][1]["evidence"] = "hid\u200bden " + "x" * 5000
    ledger["workload_brief"] = "ｂrief\u202e"
    ctx = build_review_context(ledger)
    first = ctx.review_data["findings"][0]
    assert "\u200b" not in first["evidence"]
    assert len(first["evidence"]) <= 1200
    assert ctx.review_data["workload_brief"] == "brief"


def test_a_review_without_a_stored_summary_says_so(ledger):
    del ledger["terraform_resources"]
    ctx = build_review_context(ledger)
    assert ctx.review_data["terraform_resources"] == {
        "resources": [],
        "available": False,
        "note": NO_RESOURCES_NOTE,
    }
    assert ctx.resource_addresses == set()


def test_an_oversized_review_is_trimmed_lowest_priority_first(ledger):
    template = ledger["findings"][0]
    ledger["findings"] = [
        {
            **template,
            "finding_id": f"id-{i}",
            "type": "deterministic-rule-result" if i == 0 else "fact",
            "evidence": "e" * 1100,
            "risk_impact": "r" * 1100,
            "recommendation": "c" * 1100,
        }
        for i in range(40)
    ]
    ctx = build_review_context(ledger)
    assert len(json.dumps(ctx.review_data, ensure_ascii=False)) <= REVIEW_BLOCK_CHARS
    first = ctx.review_data["findings"][0]
    # The high-risk finding keeps its detail; the cut came from the end.
    assert first["priority"] == "high" and first["evidence"]
    assert ctx.review_data["findings"][-1]["evidence"] == ""


def test_deeper_findings_point_at_their_parent_by_alias(ledger):
    ledger["findings"][2]["parent_finding_id"] = RULE_FINDING_ID
    ctx = build_review_context(ledger)
    deeper = next(f for f in ctx.review_data["findings"] if f["ref"] == "F2")
    assert deeper["deeper_analysis_of"] == "F1"


def test_findings_trimmed_out_of_the_prompt_cannot_be_cited(ledger):
    template = ledger["findings"][0]
    ledger["findings"] = [
        {
            **template,
            "finding_id": f"id-{i}",
            "evidence": "e" * 1200,
            "finding": "f" * 1200,
        }
        for i in range(60)
    ]
    ctx = build_review_context(ledger)
    shown = {f["ref"] for f in ctx.review_data["findings"]}
    assert ctx.review_data.get("omitted_findings")
    assert set(ctx.finding_ids) == shown
