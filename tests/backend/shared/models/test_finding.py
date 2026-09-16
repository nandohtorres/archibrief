import uuid

import pytest
from pydantic import ValidationError

from backend.shared.models.finding import (
    ConfidenceInputs,
    Finding,
    FindingCategory,
    FindingType,
)


def _base_kwargs(**overrides):
    kwargs = dict(
        finding_id=str(uuid.uuid4()),
        review_id="review-1",
        category=FindingCategory.IAM,
        type=FindingType.DETERMINISTIC_RULE_RESULT,
        finding="text",
        evidence="evidence",
        citation=None,
        confidence=0.9,
        confidence_inputs=ConfidenceInputs(
            evidence_directness=1.0, source_agreement=1.0, rule_determinism=1.0
        ),
        risk_impact="impact",
        recommendation="fix it",
        framework_mapping=["AWS Well-Architected: Security Pillar"],
        depth_level="lightweight",
    )
    kwargs.update(overrides)
    return kwargs


def test_deterministic_rule_result_allows_no_citation():
    finding = Finding(**_base_kwargs())
    assert finding.type == FindingType.DETERMINISTIC_RULE_RESULT


def test_fact_requires_citation():
    with pytest.raises(ValidationError):
        Finding(**_base_kwargs(type=FindingType.FACT, citation=None))


def test_not_observable_rejects_citation():
    citation_kwargs = _base_kwargs(type=FindingType.NOT_OBSERVABLE)
    citation_kwargs["citation"] = {
        "source_url": "https://example.com",
        "source_edition": "2026",
        "retrieved_at": "2026-09-08T00:00:00",
        "document_id": "doc-1",
        "content_hash": "abc123",
        "heading_path": "root",
        "exact_text_span": "span",
        "parser_version": "v1",
        "corpus_version": "v1",
    }
    with pytest.raises(ValidationError):
        Finding(**citation_kwargs)


def test_confidence_out_of_range_rejected():
    with pytest.raises(ValidationError):
        Finding(**_base_kwargs(confidence=1.5))
