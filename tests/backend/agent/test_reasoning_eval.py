from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.agent.reasoning_eval import (
    EVAL_BRIEFS,
    HOLDOUT_BRIEFS,
    ExpectedFinding,
    ReasoningEvalBrief,
    score_reasoning,
)
from backend.shared.models.finding import Citation, ConfidenceInputs, Finding


def _make_finding(
    finding_text: str,
    evidence: str = "",
    risk_impact: str = "",
    category: str = "iam",
    document_id: str = "waf-security-pillar",
    citation: bool = True,
    finding_type: str = "fact",
) -> Finding:
    return Finding(
        finding_id="f-" + str(hash((finding_text, evidence)) % 10_000),
        review_id="test",
        category=category,
        type=finding_type,
        finding=finding_text,
        evidence=evidence,
        citation=(
            Citation(
                source_url="https://example.com",
                source_edition=None,
                retrieved_at=datetime.now(UTC),
                document_id=document_id,
                chunk_id="chunk-1",
                content_hash="abc",
                heading_path="A > B",
                exact_text_span="some real span",
                parser_version="1.0",
                corpus_version="v1",
            )
            if citation
            else None
        ),
        confidence=0.9,
        confidence_inputs=ConfidenceInputs(
            evidence_directness=0.9, source_agreement=0.9, rule_determinism=0.5
        ),
        risk_impact=risk_impact,
        recommendation="do something",
        framework_mapping=[],
        alternatives_considered=[],
        depth_level="lightweight",
    )


_EXPECTED = ExpectedFinding(
    topic_id="root-mfa",
    category="iam",
    description="Root user has no MFA.",
    keyword_groups=[["root"], ["mfa"]],
    negative_phrases=["mfa is already enabled", "mfa is already configured"],
    plausible_source_documents=["waf-security-pillar", "iam-best-practices"],
)
_BRIEF = ReasoningEvalBrief(
    brief_id="test-brief",
    workload_brief="brief text",
    retrieval_query="query text",
    expected_findings=[_EXPECTED],
)


def test_topic_covered_when_all_keyword_groups_match():
    finding = _make_finding("Root user has no MFA configured, a critical exposure.")
    result = score_reasoning([finding], _BRIEF)
    assert result["topic_recall"] == 1.0
    assert result["topic_hits"][0]["covered"] is True
    covering = result["topic_hits"][0]["covered_by_findings"]
    assert len(covering) == 1
    assert covering[0]["finding"]["finding_id"] == finding.finding_id
    assert covering[0]["precision_label"] is None


def test_topic_not_covered_when_negative_phrase_present():
    # contains both "root" and "mfa" but asserts the OPPOSITE state —
    # must not count as coverage (pure substring matching can't tell this
    # apart from a real gap)
    finding = _make_finding("Root user's MFA is already enabled and enforced.")
    result = score_reasoning([finding], _BRIEF)
    assert result["topic_hits"][0]["covered"] is False


def test_not_observable_finding_never_counts_as_coverage():
    finding = _make_finding(
        "Whether root MFA is configured cannot be verified from the provided brief.",
        finding_type="not-observable",
        citation=False,
    )
    result = score_reasoning([finding], _BRIEF)
    assert result["topic_hits"][0]["covered"] is False


def test_topic_not_covered_when_only_some_keyword_groups_match():
    # mentions "root" but never "mfa" — must not count as a match, AND
    # semantics require every group to have a hit
    finding = _make_finding("The root user's password policy is weak.")
    result = score_reasoning([finding], _BRIEF)
    assert result["topic_recall"] == 0.0
    assert result["topic_hits"][0]["covered"] is False


def test_matching_is_case_and_whitespace_insensitive():
    finding = _make_finding("ROOT   user has no\nMFA   enabled at all.")
    result = score_reasoning([finding], _BRIEF)
    assert result["topic_hits"][0]["covered"] is True


def test_citation_from_plausible_source_flagged_plausible_when_matching():
    finding = _make_finding("Root user has no MFA.", document_id="waf-security-pillar")
    result = score_reasoning([finding], _BRIEF)
    assert result["topic_hits"][0]["citation_relevance"] == "plausible"


def test_citation_from_implausible_source_flagged_implausible_not_rejected():
    # still counts as covered (recall isn't penalized), but the flag says
    # the citation came from an unexpected document, for human review
    finding = _make_finding(
        "Root user has no MFA.", document_id="waf-cost-optimization-pillar"
    )
    result = score_reasoning([finding], _BRIEF)
    assert result["topic_hits"][0]["covered"] is True
    assert result["topic_hits"][0]["citation_relevance"] == "implausible"


def test_fact_type_finding_without_citation_is_rejected_by_finding_schema():
    # Documents why score_reasoning's "missing" citation_relevance branch
    # is defensive code rather than something a real Finding can exercise
    # today: Finding's own model_validator (backend/shared/models/
    # finding.py) requires a citation for every type except
    # not-observable and deterministic-rule-result, and neither of those
    # can ever cover a topic (not-observable is explicitly excluded in
    # _finding_covers_topic; deterministic-rule-result findings are never
    # passed into score_reasoning at all — see this file's module
    # docstring). So the construction itself must fail with a
    # ValidationError.
    with pytest.raises(ValidationError):
        _make_finding("Root user has no MFA.", citation=False)


def test_citation_relevance_is_none_when_topic_not_covered_at_all():
    finding = _make_finding("Completely unrelated finding about cost tagging.")
    result = score_reasoning([finding], _BRIEF)
    assert result["topic_hits"][0]["covered"] is False
    assert result["topic_hits"][0]["citation_relevance"] is None


def test_unmatched_findings_are_reported_not_penalized():
    matching = _make_finding("Root user has no MFA configured.")
    extra = _make_finding(
        "Separately, S3 versioning is also disabled.", category="recovery"
    )
    result = score_reasoning([matching, extra], _BRIEF)
    assert result["topic_recall"] == 1.0  # extra finding doesn't lower recall
    assert len(result["unmatched_findings"]) == 1
    assert result["unmatched_findings"][0]["finding"]["finding_id"] == extra.finding_id
    assert result["unmatched_findings"][0]["precision_label"] is None


def test_multiple_findings_can_jointly_cover_one_topic():
    partial_a = _make_finding("The root account exists with default settings.")
    partial_b = _make_finding("MFA is not enforced anywhere in this account.")
    result = score_reasoning([partial_a, partial_b], _BRIEF)
    # neither finding alone contains both "root" and "mfa", so neither
    # individually covers the topic — this is deliberate: covering a topic
    # requires ONE finding to substantiate it, not fragments spread across
    # multiple findings a reviewer would have to mentally combine.
    assert result["topic_hits"][0]["covered"] is False


def test_empty_expected_findings_yields_full_recall_by_convention():
    brief = ReasoningEvalBrief(
        brief_id="empty", workload_brief="x", retrieval_query="y", expected_findings=[]
    )
    result = score_reasoning([], brief)
    assert (
        result["topic_recall"] == 0.0
    )  # total=0 -> defined as 0.0, not divide-by-zero
    assert result["topics_total"] == 0


@pytest.mark.parametrize("briefs", [EVAL_BRIEFS, HOLDOUT_BRIEFS])
def test_brief_ids_are_unique(briefs):
    ids = [b.brief_id for b in briefs]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("briefs", [EVAL_BRIEFS, HOLDOUT_BRIEFS])
def test_every_brief_has_at_least_one_expected_finding(briefs):
    for brief in briefs:
        assert len(brief.expected_findings) >= 1, brief.brief_id


@pytest.mark.parametrize("briefs", [EVAL_BRIEFS, HOLDOUT_BRIEFS])
def test_every_expected_finding_has_nonempty_keyword_groups(briefs):
    for brief in briefs:
        for expected in brief.expected_findings:
            assert expected.keyword_groups, f"{brief.brief_id}/{expected.topic_id}"
            for group in expected.keyword_groups:
                assert group, (
                    f"{brief.brief_id}/{expected.topic_id} has an empty keyword group"
                )


@pytest.mark.parametrize("briefs", [EVAL_BRIEFS, HOLDOUT_BRIEFS])
def test_every_expected_finding_has_plausible_source_documents(briefs):
    for brief in briefs:
        for expected in brief.expected_findings:
            assert expected.plausible_source_documents, (
                f"{brief.brief_id}/{expected.topic_id}"
            )


@pytest.mark.parametrize("briefs", [EVAL_BRIEFS, HOLDOUT_BRIEFS])
def test_retrieval_query_plausibly_targets_every_expected_topic(briefs):
    """Regression guard for the r01/r02 retrieval/reasoning confound: a
    brief's retrieval_query should mention
    at least one keyword from EVERY expected topic's first keyword group,
    so a miss on that topic can plausibly be attributed to reasoning, not
    retrieval never having a chance to surface relevant evidence at all.
    A structural/textual check only — doesn't guarantee real embedding-
    based retrieval finds it — but catches a future brief edit that
    reintroduces the same confound."""
    for brief in briefs:
        query_lower = brief.retrieval_query.lower()
        for expected in brief.expected_findings:
            first_group = expected.keyword_groups[0]
            assert any(kw.lower() in query_lower for kw in first_group), (
                f"{brief.brief_id}/{expected.topic_id}: retrieval_query doesn't "
                f"mention any of {first_group}"
            )


def test_dev_and_holdout_brief_ids_do_not_overlap():
    dev_ids = {b.brief_id for b in EVAL_BRIEFS}
    holdout_ids = {b.brief_id for b in HOLDOUT_BRIEFS}
    assert not (dev_ids & holdout_ids)


def test_rule_findings_in_briefs_validate_as_real_findings():
    """Any brief that ships mocked rule_findings must actually validate as
    real Finding objects — resolve_rule_findings() in reason.py would
    otherwise raise FindingValidationError on a real run, wasting the
    Bedrock call that already happened before it's reached."""
    from backend.agent.nodes.reason import resolve_rule_findings

    for brief in EVAL_BRIEFS + HOLDOUT_BRIEFS:
        if brief.rule_findings:
            resolve_rule_findings(brief.rule_findings)  # raises on failure
