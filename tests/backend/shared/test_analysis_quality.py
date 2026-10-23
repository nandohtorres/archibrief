import json

import pytest

from backend.chat.context import build_review_context
from backend.shared.analysis_quality import (
    build_analysis_quality,
    public_analysis_quality,
    stage_counts,
)
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
