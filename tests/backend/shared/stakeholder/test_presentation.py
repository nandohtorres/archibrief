"""Stakeholder Brief presentation facts (ADR-0062).

The report carries a rule finding's concern and subject, never prices or
the old stakeholder card, and title inference never assigns a risk.
"""

import json
import re

import pytest

from backend.shared.assessment import finding_assessment
from backend.shared.models.finding import (
    ConfidenceInputs,
    Finding,
    FindingCategory,
    FindingType,
    PlainLanguage,
)
from backend.shared.report import build_review_report
from backend.shared.stakeholder.catalog import RECIPES
from backend.shared.stakeholder.presentation import brief_meta

_AMOUNT = re.compile(r"\$\s?\d|\bUSD\s?\d|monthly_known|effort_hours")


def _finding(
    finding_id: str,
    title: str,
    *,
    concern: str | None = None,
) -> Finding:
    return Finding(
        finding_id=finding_id,
        review_id="r1",
        category=FindingCategory.EXPOSURE,
        type=FindingType.DETERMINISTIC_RULE_RESULT,
        finding=title,
        evidence='resource "aws_db_instance" "main" { name = "${var.name}" }',
        confidence=1.0,
        confidence_inputs=ConfidenceInputs(
            evidence_directness=1, source_agreement=1, rule_determinism=1
        ),
        risk_impact="risk",
        recommendation="fix",
        framework_mapping=[],
        depth_level="lightweight",
        concern=concern,
    )


def _plain() -> PlainLanguage:
    return PlainLanguage(
        written_by="model",
        title="Backups",
        analogy="Like a spare key.",
        what_could_happen="Data loss.",
        action="Add backups.",
        needs_action=True,
        severity="medium",
        effort_hours_low=1,
        effort_hours_high=2,
    )


def test_recorded_concern_is_passed_through():
    meta = brief_meta(
        _finding("f1", "RDS instance 'main' has no Multi-AZ", concern="rds_multi_az")
    )
    assert meta == {
        "version": 2,
        "concern": "rds_multi_az",
        "concern_source": "recorded",
        "subject": "main",
    }


def test_old_findings_get_a_title_inferred_concern_but_no_risk():
    title = "No aws_cloudtrail resource found in the submitted Terraform"
    finding = _finding("f1", title)
    assert brief_meta(finding)["concern"] == "cloudtrail_present"
    assert brief_meta(finding)["concern_source"] == "title"
    assert finding_assessment(finding.model_dump(mode="json"))["action"] == "unknown"


def test_unknown_titles_stay_unclassified():
    meta = brief_meta(_finding("f1", "Something no rule has ever said"))
    assert meta["concern"] is None
    assert meta["concern_source"] is None


@pytest.mark.parametrize(
    "finding_type", [FindingType.INFERENCE, FindingType.NOT_OBSERVABLE]
)
def test_only_rule_findings_get_a_brief_block(finding_type):
    finding = _finding("m1", "x").model_copy(
        update={"type": finding_type, "plain": _plain()}
    )
    assert brief_meta(finding) is None


def test_report_has_no_prices_and_keeps_records_and_assessments():
    findings = [
        _finding("f1", "RDS instance 'main' has no Multi-AZ", concern="rds_multi_az"),
        _finding("f2", "No aws_cloudtrail resource found in the submitted Terraform"),
        _finding("m1", "model").model_copy(
            update={"type": FindingType.NOT_OBSERVABLE, "plain": _plain()}
        ),
    ]
    ledger = {
        "findings": [f.model_dump(mode="json") for f in findings],
        "terraform_resources": {"resources": []},
        "baseline_answers": [],
    }
    report = build_review_report({"reviewId": "r1"}, ledger)
    assert "budget" not in report
    entries = {e["record"]["finding_id"]: e for e in report["findings"]}
    assert all("stakeholder" not in e for e in entries.values())
    assert entries["f1"]["brief"]["concern"] == "rds_multi_az"
    assert entries["f2"]["brief"]["concern_source"] == "title"
    assert "brief" not in entries["m1"]
    # Stored records and assessments are unchanged.
    for finding in findings:
        record = finding.model_dump(mode="json")
        assert entries[finding.finding_id]["record"] == record
        assert entries[finding.finding_id]["assessment"] == finding_assessment(record)
    assert entries["f1"]["assessment"]["severity"] == RECIPES["rds_multi_az"].severity
    # No monetary estimate anywhere outside the stored records; literal
    # Terraform syntax in evidence is kept.
    presentation = {k: v for k, v in report.items() if k != "findings"}
    presentation["findings"] = [
        {k: v for k, v in e.items() if k != "record"} for e in entries.values()
    ]
    assert not _AMOUNT.search(json.dumps(presentation))
    assert "${var.name}" in entries["f1"]["record"]["evidence"]
