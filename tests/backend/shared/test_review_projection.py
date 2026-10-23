import copy

from backend.chat.context import build_review_context
from backend.shared.analysis_quality import build_analysis_quality, stage_counts
from backend.shared.models.finding import Finding
from backend.shared.report import build_review_report
from backend.shared.review_projection import assemble_current_ledger


def _record(fid="base", **overrides):
    return Finding.model_validate(
        {
            "finding_id": fid,
            "review_id": "r1",
            "category": "iam",
            "type": "deterministic-rule-result",
            "concern": "ec2_imdsv2",
            "finding": 'EC2 instance "app" permits IMDSv1',
            "evidence": 'resource "aws_instance" "app"',
            "confidence": 1,
            "confidence_inputs": {
                "evidence_directness": 1,
                "source_agreement": 1,
                "rule_determinism": 1,
            },
            "risk_impact": "risk",
            "recommendation": "fix",
            "framework_mapping": [],
            "depth_level": "lightweight",
            "created_at": "2026-10-23T00:00:00Z",
            **overrides,
        }
    ).model_dump(mode="json")


def _item(fid="child", **overrides):
    return {
        **_record(fid, parent_finding_id="base", depth_level="deep"),
        "reviewId": "r1",
        "findingId": fid,
        "ttl": 1000,
        **overrides,
    }


def test_projection_keeps_base_immutable_and_filters_identity_expiry_and_orphans():
    ledger = {"findings": [_record()]}
    before = copy.deepcopy(ledger)
    current = assemble_current_ledger(
        ledger,
        "r1",
        [
            _item(),
            _item(),
            _item("expired", ttl=1),
            _item("other-review", review_id="r2"),
            _item("orphan", parent_finding_id="missing"),
        ],
        now=100,
    )
    assert ledger == before
    assert [f["finding_id"] for f in current["findings"]] == ["base", "child"]
    assert current["report_projection"]["excluded_child_count"] == 2
    assert current["finding_count"] == 2


def test_incomplete_batch_is_not_published_as_a_complete_saved_run():
    marker = {
        "reviewId": "r1",
        "kind": "deeper-result",
        "parent_finding_id": "base",
        "finding_ids": ["child", "missing"],
        "ttl": 1000,
    }
    current = assemble_current_ledger(
        {"findings": [_record()]}, "r1", [_item(), marker], now=100
    )
    assert len(current["findings"]) == 1
    assert current["report_projection"]["excluded_child_count"] > 0


def test_report_budget_diagram_and_chat_project_the_same_children():
    graph = {
        "version": 1,
        "nodes": [
            {
                "id": "aws_instance.app",
                "type": "aws_instance",
                "name": "app",
                "findings": ["base"],
            }
        ],
        "edges": [],
    }
    quality = build_analysis_quality(
        stage_counts(1, 1), [{"model_id": "m"}], [{"model_id": "m"}]
    )
    ledger = assemble_current_ledger(
        {"findings": [_record()], "architecture": graph},
        "r1",
        [_item(analysis_quality=quality)],
        now=100,
    )
    report = build_review_report({"reviewId": "r1"}, ledger)
    assert {row["finding_id"] for row in report["budget"]["rows"]} == {"base", "child"}
    assert set(report["architecture"]["nodes"][0]["findings"]) == {"base", "child"}
    ctx = build_review_context(ledger)
    assert ctx.alias_for("child") is not None
    assert ctx.review_data["deeper_reviews"][0]["analysis_quality"] == quality


def test_older_configuration_does_not_claim_children_were_read():
    current = assemble_current_ledger(
        {"findings": []}, "r1", [], children_available=False
    )
    assert current["report_projection"]["children_available"] is False
