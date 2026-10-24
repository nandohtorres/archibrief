from backend.shared.models.finding import (
    ConfidenceInputs,
    Finding,
    FindingCategory,
    FindingType,
    FixComponent,
    PlainLanguage,
)
from backend.shared.report import build_review_report
from backend.shared.stakeholder.brief import (
    build_stakeholder_view,
    effort_label,
    stakeholder_block,
)


def _rule(finding_id: str, title: str, evidence: str = "", concern: str | None = None) -> Finding:
    return Finding(
        finding_id=finding_id,
        review_id="r1",
        category=FindingCategory.EXPOSURE,
        type=FindingType.DETERMINISTIC_RULE_RESULT,
        finding=title,
        evidence=evidence,
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


def _model(finding_id: str, plain: PlainLanguage | None) -> Finding:
    return _rule(finding_id, "model finding").model_copy(
        update={"type": FindingType.NOT_OBSERVABLE, "plain": plain}
    )


def _plain(**overrides) -> PlainLanguage:
    values = dict(
        written_by="model",
        title="The platform runs on one server",
        analogy="Like a shop with one cashier.",
        what_could_happen="A crash takes it offline.",
        action="Add a second server behind a load balancer.",
        needs_action=True,
        severity="high",
        harm="downtime",
        fix_components=[FixComponent(item="alb"), FixComponent(item="ec2_instance", size="t3.micro")],
        effort_hours_low=4,
        effort_hours_high=12,
    )
    values.update(overrides)
    return PlainLanguage(**values)


_RESOURCES = {
    "resources": [
        {"type": "aws_db_instance", "name": "main", "settings": {"instance_class": "db.t3.micro"}}
    ]
}
_MULTI_AZ = (
    "RDS instance 'main' is not configured multi_az",
    'resource "aws_db_instance" "main" has multi_az = false or unset',
)


def test_free_urgent_rule_fix_is_fix_today():
    block = stakeholder_block(_rule("f1", "x", concern="ec2_imdsv2"))
    assert block["verdict"] == "fix-today"
    assert block["fix"]["monthly_known"] == 0
    assert not block["fix"]["has_unpriced"]
    assert block["inaction"]["source_name"] == "IBM Cost of a Data Breach Report 2026"


def test_standby_database_is_priced_at_the_declared_instance_class():
    block = stakeholder_block(_rule("f1", *_MULTI_AZ, concern="rds_multi_az"), _RESOURCES)
    assert block["fix"]["monthly_known"] == round(0.017 * 730, 2)
    assert block["verdict"] == "when-budget-allows"
    assert block["subject"] == "main"


def test_unknown_size_is_unpriced_not_guessed():
    block = stakeholder_block(_rule("f1", *_MULTI_AZ, concern="rds_multi_az"), None)
    assert block["fix"]["monthly_known"] == 0
    assert block["fix"]["has_unpriced"] is True


def test_older_findings_get_their_concern_from_the_title():
    block = stakeholder_block(_rule("f1", "No aws_cloudtrail resource found in the submitted Terraform"))
    assert block["concern"] == "cloudtrail_present"


def test_downtime_harm_uses_the_availability_target():
    answers = [{"field": "availability_criticality", "value": "customer-facing, 99.9% target"}]
    block = stakeholder_block(_model("m1", _plain()), None, answers)
    assert "99.9% availability target allows about 44 minutes" in block["inaction"]["detail"]
    assert block["inaction"]["method"]


def test_model_findings_use_their_plain_block_and_code_prices_it():
    block = stakeholder_block(_model("m1", _plain()))
    assert block["source"] == "model"
    assert block["fix"]["monthly_known"] == round((0.0225 + 0.008) * 730 + 0.0104 * 730, 2)
    assert block["verdict"] == "worth-the-money"


def test_findings_with_nothing_to_fix_stay_out_of_the_budget():
    view = build_stakeholder_view(
        [
            _model("m1", _plain(needs_action=False, fix_components=[], harm=None)),
            _model("m2", None),
            _rule("f1", "x", concern="ec2_imdsv2"),
        ]
    )
    assert set(view["blocks"]) == {"m1", "f1"}
    assert view["blocks"]["m1"]["fix"] is None
    assert view["budget"]["item_count"] == 1
    assert view["budget"]["free_count"] == 1


def test_budget_totals_and_order():
    view = build_stakeholder_view(
        [
            _rule("f1", *_MULTI_AZ, concern="rds_multi_az"),
            _model("m1", _plain()),
            _rule("f2", "x", concern="iam_wildcard"),
            _rule("f3", "x", concern="cloudtrail_present"),
        ],
        _RESOURCES,
    )
    budget = view["budget"]
    assert [row["finding_id"] for row in budget["rows"]] == ["f2", "m1", "f3", "f1"]
    assert budget["monthly_optional"] == round(0.017 * 730, 2)
    assert budget["monthly_recommended"] == view["blocks"]["m1"]["fix"]["monthly_known"]
    assert budget["unpriced_items"] == ["CloudTrail audit log"]
    assert budget["verdict_counts"]["fix-today"] == 1
    assert budget["prices_as_of"] == "2026-10"


def test_effort_labels():
    assert effort_label(0.25, 0.5) == "15 to 30 minutes"
    assert effort_label(0.5, 2) == "30 minutes to 2 hours"
    assert effort_label(2, 8) == "2 to 8 hours"
    assert effort_label(1, 1) == "about 1 hour"
    assert effort_label(4, 16) == "0.5 to 2 working days"


def test_report_carries_the_cards_and_budget():
    ledger = {
        "findings": [_rule("f1", *_MULTI_AZ, concern="rds_multi_az").model_dump(mode="json")],
        "terraform_resources": _RESOURCES,
        "baseline_answers": [],
    }
    report = build_review_report({"reviewId": "r1"}, ledger)
    assert report["findings"][0]["stakeholder"]["concern"] == "rds_multi_az"
    assert report["budget"]["item_count"] == 1


def test_unassessed_findings_stay_in_the_budget():
    # An older finding has no concern key, so its assessment is unknown, but
    # report pricing and aggregation still treat it as they always have.
    title = "No aws_cloudtrail resource found in the submitted Terraform"
    ledger = {"findings": [_rule("f1", title).model_dump(mode="json")]}
    report = build_review_report({"reviewId": "r1"}, ledger)
    assert report["findings"][0]["assessment"]["action"] == "unknown"
    assert report["findings"][0]["stakeholder"]["concern"] == "cloudtrail_present"
    assert report["budget"]["item_count"] == 1


def test_a_failing_view_never_fails_the_report(monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("backend.shared.report.build_stakeholder_view", broken)
    ledger = {"findings": [_rule("f1", "x", concern="ec2_imdsv2").model_dump(mode="json")]}
    report = build_review_report({"reviewId": "r1"}, ledger)
    assert "budget" not in report
    assert "stakeholder" not in report["findings"][0]


def test_a_fix_with_no_listed_harm_still_gets_both_cost_boxes():
    block = stakeholder_block(_model("m1", _plain(harm=None)))
    assert block["fix"] is not None
    assert block["inaction"]["method"]


def test_optional_usage_items_dont_mark_the_recommended_total_unpriced():
    view = build_stakeholder_view(
        [
            _rule("f1", "x", concern="ec2_imdsv2"),
            _model("m1", _plain(severity="low", fix_components=[FixComponent(item="log_ingestion")])),
        ]
    )
    assert view["blocks"]["m1"]["verdict"] == "when-budget-allows"
    assert view["budget"]["recommended_has_unpriced"] is False
    assert view["budget"]["unpriced_items"] == ["Access logs"]
