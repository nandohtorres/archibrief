import json

import pytest

from backend.chat.context import build_review_context
from backend.shared.analysis_quality import (
    build_analysis_quality,
    public_analysis_quality,
    public_analysis_scope,
    stage_counts,
)


def test_analysis_scope_is_allowlisted_and_never_claims_runtime_verification():
    raw = {
        "version": "terraform-observations@2026-10-23",
        "facts_emitted": 10,
        "omitted_resources": 2,
        "omitted_items": 0,
        "incomplete_resources": 1,
        "runtime_verified": True,
        "private": "PRIVATE-CANARY",
    }
    public = public_analysis_scope(raw)
    assert public["truncated"] is True
    assert public["runtime_verified"] is False
    assert "PRIVATE-CANARY" not in json.dumps(public)
    assert public_analysis_scope({**raw, "omitted_resources": True}) is None
    assert public_analysis_scope(None) is None


from backend.shared.report import build_review_report


@pytest.mark.parametrize(
    ("counts", "candidates", "valid", "outcome"),
    [
        (
            stage_counts(2, 2),
            [{}, {}],
            [{"model_id": "m"}, {"model_id": "m"}],
            "complete",
        ),
        (stage_counts(2, 1), [{}], [{"model_id": "m"}], "partial"),
        (stage_counts(2, 1), [{}], [], "all-rejected"),
        (stage_counts(2, 0), [{}], [{}], "rules-only"),
        (stage_counts(0, 0), [], [], "no-findings"),
        (None, [], [], "unknown"),
        (None, [{}], [], "partial"),
    ],
)
def test_quality_distinguishes_pipeline_completion_from_retained_output(
    counts, candidates, valid, outcome
):
    quality = build_analysis_quality(counts, candidates, valid)
    assert quality["outcome"] == outcome
    assert public_analysis_quality(quality) == quality


@pytest.mark.parametrize(
    ("valid", "outcome"), [([{}, {}], "rules-only"), ([], "no-findings")]
)
def test_an_unavailable_model_is_named_rather_than_reported_as_rejections(valid, outcome):
    quality = build_analysis_quality(None, [{}, {}], valid, model_unavailable=True)
    assert quality["outcome"] == outcome
    assert quality["model_verification"] == {"attempted": 0, "accepted": 0, "rejected": 0}
    assert quality["reason_codes"][0] == "model_unavailable"
    assert public_analysis_quality(quality) == quality


def test_rejections_at_two_gates_are_counted_separately_and_never_leak_text():
    quality = build_analysis_quality(
        stage_counts(4, 2), [{"secret": "PRIVATE"}, {}], [{"model_id": "m"}]
    )
    assert quality["model_verification"]["rejected"] == 2
    assert quality["schema_validation"]["rejected"] == 1
    assert "PRIVATE" not in json.dumps(quality)
    assert quality["reason_codes"] == [
        "model_verification_rejected",
        "schema_validation_rejected",
    ]


def test_report_and_chat_publish_the_same_quality_and_old_reports_stay_unknown():
    quality = build_analysis_quality(stage_counts(1, 0), [], [])
    ledger = {"findings": [], "analysis_quality": quality}
    assert build_review_report({"reviewId": "r"}, ledger)["analysis_quality"] == quality
    assert build_review_context(ledger).review_data["analysis_quality"] == quality
    assert (
        build_review_report({"reviewId": "r"}, {"findings": []})["analysis_quality"][
            "outcome"
        ]
        == "unknown"
    )


def test_invalid_counts_do_not_become_a_complete_report():
    invalid = {
        "version": 1,
        "outcome": "complete",
        "model_verification": {"attempted": 1, "accepted": 4, "rejected": 0},
    }
    assert public_analysis_quality(invalid)["outcome"] == "unknown"
