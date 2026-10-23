from backend.shared.models.finding import (
    Citation,
    ConfidenceInputs,
    DepthLevel,
    Finding,
    FindingCategory,
    FindingType,
)
from backend.shared.report import build_review_report, compute_presentation

_CITATION = Citation(
    source_url="https://example.com",
    source_edition=None,
    retrieved_at="2026-09-01T00:00:00Z",
    document_id="doc",
    chunk_id="c1",
    content_hash="h1",
    heading_path="h",
    exact_text_span="span",
    parser_version="v1",
    corpus_version="v1",
)


def _finding(**overrides) -> Finding:
    defaults = dict(
        finding_id="f1",
        review_id="r1",
        category=FindingCategory.IAM,
        type=FindingType.NOT_OBSERVABLE,
        finding="finding text",
        evidence="evidence text",
        citation=None,
        confidence=0.5,
        confidence_inputs=ConfidenceInputs(
            evidence_directness=0.5, source_agreement=0.5, rule_determinism=0.5
        ),
        risk_impact="low",
        recommendation="do nothing",
        framework_mapping=[],
        depth_level=DepthLevel.LIGHTWEIGHT,
    )
    defaults.update(overrides)
    if (
        defaults["type"] != FindingType.NOT_OBSERVABLE
        and defaults.get("citation") is None
    ):
        defaults["citation"] = _CITATION
    return Finding(**defaults)


def test_compute_presentation_matches_fixture_examples():
    assert compute_presentation(
        _finding(
            type=FindingType.DETERMINISTIC_RULE_RESULT,
            category=FindingCategory.EXPOSURE,
        )
    ) == {
        "priority": "high",
        "short_label": "Rule result",
    }
    assert compute_presentation(_finding(type=FindingType.FACT)) == {
        "priority": "confirmed",
        "short_label": "Reported fact",
    }
    assert compute_presentation(_finding(type=FindingType.ASSUMPTION)) == {
        "priority": "review",
        "short_label": "Review",
    }
    assert compute_presentation(_finding(type=FindingType.NOT_OBSERVABLE)) == {
        "priority": "unknown",
        "short_label": "Not observable",
    }


def test_build_review_report_assembles_full_contract_shape():
    review_item = {
        "reviewId": "r1",
        "status": "complete",
        "completedAt": "2026-10-01T00:00:00Z",
    }
    ledger = {
        "workload_brief": "a 3-tier app",
        "baseline_answers": [
            {
                "field": "x",
                "label": "X",
                "outcome": "answered",
                "value": "y",
                "policy_version": "v1",
            }
        ],
        "findings": [_finding().model_dump(mode="json")],
        "generated_at": "2026-10-01T00:05:00Z",
    }

    report = build_review_report(review_item, ledger)

    assert report["review_id"] == "r1"
    assert report["status"] == "complete"
    assert report["baseline_answers"][0]["field"] == "x"
    assert len(report["findings"]) == 1
    assert report["findings"][0]["record"]["finding_id"] == "f1"
    assert report["findings"][0]["presentation"]["priority"] == "unknown"
    # Flagged placeholders, not fabricated — present and contract-shaped.
    assert report["owner_id"] == "admin"
    assert report["cost_estimate_tier"] in ("low", "medium", "high")


def test_build_review_report_defaults_baseline_answers_to_empty_list():
    review_item = {"reviewId": "r1", "completedAt": "2026-10-01T00:00:00Z"}
    ledger = {"findings": []}
    report = build_review_report(review_item, ledger)
    assert report["baseline_answers"] == []
    assert report["findings"] == []


def test_report_carries_the_architecture_when_the_ledger_has_one():
    from backend.shared.report import build_review_report

    graph = {"version": 1, "nodes": [], "edges": []}
    item = {"reviewId": "r1"}
    assert (
        build_review_report(item, {"findings": [], "architecture": graph})[
            "architecture"
        ]
        == graph
    )
    assert "architecture" not in build_review_report(item, {"findings": []})
