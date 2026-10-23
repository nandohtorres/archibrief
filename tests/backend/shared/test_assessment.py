import pytest

from backend.shared.assessment import assessment_rank, finding_assessment


@pytest.mark.parametrize("kind", ["fact", "inference", "assumption", "recommendation"])
def test_evidence_type_does_not_assign_severity(kind):
    assessment = finding_assessment(
        {"type": kind, "confidence": 1, "risk_impact": "critical"}
    )
    assert assessment == {
        "version": 1,
        "severity": None,
        "action": "unknown",
        "source": "unassessed",
    }


def test_rule_assessment_requires_explicit_catalog_key():
    rule = {"type": "deterministic-rule-result", "concern": "s3_encryption"}
    assert finding_assessment(rule)["severity"] == "medium"
    assert finding_assessment(rule)["source"] == "rule"
    assert (
        finding_assessment({"type": rule["type"], "finding": "S3 encryption"})[
            "severity"
        ]
        is None
    )


def test_risky_fact_ranks_ahead_of_medium_rule_and_no_action_fact():
    risky = {
        "type": "fact",
        "plain": {"written_by": "model", "needs_action": True, "severity": "critical"},
    }
    medium = {"type": "deterministic-rule-result", "concern": "s3_encryption"}
    safe = {
        "type": "fact",
        "plain": {"written_by": "reviewer", "needs_action": False, "severity": "low"},
    }
    assert (
        assessment_rank(risky)
        < assessment_rank(medium)
        < assessment_rank({})
        < assessment_rank(safe)
    )
    assert finding_assessment(safe)["severity"] is None


def test_missing_evidence_and_malformed_plain_do_not_become_assessed():
    plain = {"written_by": "model", "needs_action": True, "severity": "critical"}
    assert (
        finding_assessment({"type": "not-observable", "plain": plain})["action"]
        == "unknown"
    )
    plain["needs_action"] = "true"
    assert (
        finding_assessment({"type": "fact", "plain": plain})["source"] == "unassessed"
    )
