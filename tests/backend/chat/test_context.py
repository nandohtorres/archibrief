"""What the chat model is told about a review (ADR-0050 §3)."""

from __future__ import annotations

import json

from backend.chat.context import (
    NO_RESOURCES_NOTE,
    REVIEW_BLOCK_CHARS,
    build_review_context,
)
from tests.backend.chat.conftest import RULE_FINDING_ID


def test_unassessed_findings_are_aliased_without_inventing_risk(ledger):
    ledger["findings"][1]["concern"] = "s3_public_access"
    ctx = build_review_context(ledger)
    assert ctx.finding_ids["F1"] == RULE_FINDING_ID  # high risk first
    assert ctx.review_data["findings"][0]["assessment"]["severity"] == "high"
    assert "priority" not in ctx.review_data["findings"][0]
    assert len(ctx.not_observable_aliases) == 1
    assert ctx.alternatives == [("F1", "AWS managed ReadOnlyAccess")]
    assert any(key.startswith("C-F") for key in ctx.finding_citations)
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
    first = next(
        f
        for f in ctx.review_data["findings"]
        if f["type"] == "deterministic-rule-result"
    )
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
            "concern": "s3_public_access" if i == 0 else None,
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
    assert first["assessment"]["severity"] == "high" and first["evidence"]
    assert ctx.review_data["findings"][-1]["evidence"] == ""


def test_summary_coverage_notices_survive_finding_trimming_and_are_bounded(ledger):
    ledger["terraform_resources"]["not_observable"] = [
        "remote module " + "x" * 500
    ] * 20
    ctx = build_review_context(ledger)
    coverage = ctx.review_data["terraform_resources"]
    assert coverage["not_observable_total"] == 20
    assert len(coverage["not_observable"]) == 10
    assert all(len(note) <= 160 for note in coverage["not_observable"])


def test_deeper_findings_point_at_their_parent_by_alias(ledger):
    ledger["findings"][2]["parent_finding_id"] = RULE_FINDING_ID
    ctx = build_review_context(ledger)
    deeper = next(f for f in ctx.review_data["findings"] if "deeper_analysis_of" in f)
    assert deeper["deeper_analysis_of"] == ctx.alias_for(RULE_FINDING_ID)


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


def test_observation_detail_is_bounded_and_omission_is_disclosed(ledger):
    ledger["terraform_resources"]["resources"] = [
        {
            "type": "aws_instance",
            "name": f"worker{i}",
            "settings": {},
            "observations": {
                "facts": [{"setting": "availability_zone", "value": "us-east-1a"}] * 200
            },
        }
        for i in range(12)
    ]
    ctx = build_review_context(ledger)
    summary = ctx.review_data["terraform_resources"]
    assert len(json.dumps(ctx.review_data, ensure_ascii=False)) <= REVIEW_BLOCK_CHARS
    assert summary["context_omitted_observation_resources"] > 0
    assert "not evidence of absence" in summary["context_scope_note"]
    assert ctx.resource_addresses == {
        f"{e['type']}.{e['name']}" for e in summary["resources"]
    }
