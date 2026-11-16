"""Offline production-path regressions for confirmed P1 remediation failures."""

from copy import deepcopy

import pytest

from backend.agent.nodes.reason import reason_node, verify_model_findings
from backend.lambdas.rule_engine.handler import (
    rule_iam_policy_wildcard_action_resource,
    rule_sqs_dlq_retention,
    run_rules,
    scanner_findings,
)
from backend.shared.recommendation_checks import (
    EBS_CAPACITY_GUIDANCE,
    unsupported_operation_reasons,
)
from backend.shared.stakeholder.catalog import infer_concern
from tests.backend.agent.nodes.test_reason import (
    _PLAIN,
    _chunk,
    _reason_state,
    _valid_finding_item,
)


@pytest.mark.parametrize(
    "finding,recommendation,plain,reason",
    [
        (
            "The scratch EBS volume is retired.",
            "Remove aws_ebs_volume.scratch. If retained, convert to gp3 and reduce size to the minimum needed.",
            None,
            "ebs_in_place_shrink",
        ),
        (
            "The scratch EBS volume is retired.",
            "Shrink the EBS volume in place after creating a smaller replacement.",
            None,
            "ebs_in_place_shrink",
        ),
        (
            "The evidence S3 bucket has no Object Lock in these files.",
            "Enable Object Lock; enabling Object Lock requires bucket recreation (cannot be added to an existing bucket).",
            None,
            "object_lock",
        ),
        (
            "The evidence S3 bucket has no Object Lock in these files.",
            "Review the actual immutability requirement first.",
            {
                "action": "Enable S3 Object Lock in COMPLIANCE mode with a 90-day retention period."
            },
            "object_lock_unscoped_compliance",
        ),
    ],
)
def test_known_bad_operations_are_blocked_or_explicitly_corrected(
    finding, recommendation, plain, reason
):
    item = _valid_finding_item(
        finding=finding,
        recommendation=recommendation,
        plain={**_PLAIN, **plain} if plain else None,
    )
    accepted, errors = verify_model_findings(
        [item],
        "review",
        "model",
        "corpus@2026-09-01",
        [_chunk("chunk-a", item["exact_quote"])],
        None,
    )
    if reason == "ebs_in_place_shrink":
        assert len(accepted) == 1 and errors == []
        assert accepted[0].recommendation == EBS_CAPACITY_GUIDANCE
        assert accepted[0].evidence == item["evidence"]
        assert accepted[0].citation.exact_text_span == item["exact_quote"]
    else:
        assert accepted == []
        assert len(errors) == 1 and reason in errors[0]


def test_a_discarded_invalid_plain_block_does_not_hide_a_safe_core_finding():
    item = _valid_finding_item(
        plain={"action": "Enable Object Lock in COMPLIANCE mode."}
    )
    accepted, errors = verify_model_findings(
        [item],
        "review",
        "model",
        "corpus@2026-09-01",
        [_chunk("chunk-a", item["exact_quote"])],
        None,
    )
    assert errors == [] and len(accepted) == 1 and accepted[0].plain is None


@pytest.mark.parametrize(
    "finding,recommendation",
    [
        (
            "The scratch EBS volume is retired.",
            "Confirm it is detached and regenerable, then remove the unused volume.",
        ),
        (
            "The EBS volume is too large.",
            "Create a smaller volume and migrate the data to it; validate the copy before switching.",
        ),
        (
            "The EBS volume is too large.",
            "Do not shrink the volume in place. Create a smaller replacement and migrate the data.",
        ),
        (
            "Object Lock is not configured in these files.",
            "Object Lock can be enabled on an existing versioned bucket. Do not recreate the bucket.",
        ),
        (
            "Object Lock is not configured in these files.",
            "Replace the bucket lifecycle configuration, then evaluate Object Lock separately.",
        ),
        (
            "Object Lock is not configured in these files.",
            "It is incorrect that Object Lock cannot be enabled on an existing bucket.",
        ),
        (
            "Object Lock is not configured in these files.",
            "Only if an immutability requirement is confirmed, evaluate COMPLIANCE mode and its irreversible consequences.",
        ),
        ("The database is undersized.", "Resize the database after capacity testing."),
    ],
)
def test_safe_or_unrelated_operations_remain_eligible(finding, recommendation):
    item = _valid_finding_item(finding=finding, recommendation=recommendation)
    accepted, errors = verify_model_findings(
        [item],
        "review",
        "model",
        "corpus@2026-09-01",
        [_chunk("chunk-a", item["exact_quote"])],
        None,
    )
    assert len(accepted) == 1 and errors == []


def _queues(source_retention):
    return {
        "resources": {
            "aws_sqs_queue": {
                "source": {
                    "message_retention_seconds": source_retention,
                    "redrive_policy": {
                        "deadLetterTargetArn": "${aws_sqs_queue.dead.arn}",
                        "maxReceiveCount": 5,
                    },
                },
                "dead": {"message_retention_seconds": 60},
            }
        }
    }


def test_daily_inspection_minimum_includes_source_age_and_recommends_a_legal_setting():
    [finding] = rule_sqs_dlq_retention(_queues(345600), "review")
    assert "432000 s" in finding.recommendation
    assert "1209600 (14 days)" in finding.recommendation


def test_no_impossible_longer_dlq_setting_when_source_already_uses_fourteen_days():
    [finding] = rule_sqs_dlq_retention(_queues(1209600), "review")
    assert "does not" not in finding.finding
    assert "outside the queue" in finding.recommendation
    assert "1296000" not in finding.recommendation


@pytest.mark.parametrize(
    "value,detail",
    [
        (0, "= 0 (automated backups disabled)"),
        (1, "= 1"),
        (None, "not declared (AWS default: 1 day)"),
        ("${var.unknown}", "could not be resolved"),
    ],
)
def test_scanner_backup_text_reports_the_actual_value(value, detail):
    body = {} if value is None else {"backup_retention_period": value}
    parsed = {"resources": {"aws_db_instance": {"db": body}}}
    scan = {
        "version": "test",
        "results": [
            {
                "check_id": "AWS-0077",
                "resource_type": "aws_db_instance",
                "resource_key": "db",
                "file": "main.tf",
                "start_line": 1,
            }
        ],
    }
    [finding] = scanner_findings(scan, parsed, "review")
    assert detail in finding.evidence
    assert "unset or 1" not in finding.evidence
    if value == 0:
        assert "disabled" in finding.finding
    elif value is None:
        assert (
            finding.finding
            == "RDS instance 'db' leaves automated-backup retention unspecified"
        )
        assert "declares" not in finding.finding
    elif value == 1:
        assert (
            finding.finding
            == "RDS instance 'db' declares 1 day(s) of automated backups"
        )
    else:
        assert (
            finding.finding
            == "RDS instance 'db' has a backup-retention scanner finding"
        )
    assert infer_concern(finding.finding) == "rds_backup_retention"
    assert "can't be restored" not in finding.risk_impact


def test_legacy_backup_title_still_maps_to_its_original_concern():
    assert (
        infer_concern("RDS instance 'old' keeps backups for one day or less")
        == "rds_backup_retention"
    )
    assert infer_concern("RDS instance 'db' has a capacity scanner finding") is None


def test_module_backup_scanner_result_stays_generic_without_guessing_retention():
    scan = {
        "version": "test",
        "results": [
            {
                "check_id": "AWS-0077",
                "resource_type": "aws_db_instance",
                "resource_key": "module",
                "scope": "module",
                "file": "main.tf",
            }
        ],
    }
    [finding] = scanner_findings(scan, {}, "review")
    assert (
        finding.finding
        == "Module call 'module' has a scanner finding for rds_backup_retention"
    )
    assert "exact resource attribution unavailable" in finding.evidence
    assert "declares" not in finding.finding and "unset or 1" not in finding.evidence


def test_retired_volume_is_preserved_with_an_explicit_safe_action_correction(capsys):
    item = _valid_finding_item(
        finding="The 1000 GB io2 EBS volume scratch remains for a retired importer.",
        recommendation="Remove the retired volume or reduce size to the minimum needed.",
        plain={**_PLAIN, "action": "Shrink the EBS volume to reduce its cost."},
    )
    original = deepcopy(item)
    accepted, errors = verify_model_findings(
        [item],
        "review",
        "model",
        "corpus@2026-09-01",
        [_chunk("chunk-a", item["exact_quote"])],
        None,
    )
    assert errors == [] and len(accepted) == 1
    result = accepted[0]
    assert result.finding == item["finding"] and result.evidence == item["evidence"]
    assert result.recommendation == result.plain.action == EBS_CAPACITY_GUIDANCE
    assert len(EBS_CAPACITY_GUIDANCE) <= 400
    assert unsupported_operation_reasons(result.model_dump(mode="json")) == []
    assert item == original
    assert '"event": "model_remediation_adjusted"' in capsys.readouterr().out


@pytest.mark.parametrize(
    "finding,evidence,action",
    [
        ("The EBS volume is unencrypted.", "encrypted=false", "Shrink the EBS volume."),
        (
            "This unused EBS volume can be shrunk in place.",
            "unused",
            "Shrink the EBS volume.",
        ),
        (
            "The retired EBS volume and KMS key need changes.",
            "KMS key archive is used.",
            "Shrink the volume and remove the KMS key archive.",
        ),
    ],
)
def test_ebs_correction_does_not_salvage_other_defects_or_mixed_unsafe_advice(
    finding, evidence, action
):
    item = _valid_finding_item(
        finding=finding, evidence=evidence, recommendation=action
    )
    accepted, errors = verify_model_findings(
        [item],
        "review",
        "model",
        "corpus@2026-09-01",
        [_chunk("chunk-a", item["exact_quote"])],
        None,
    )
    assert accepted == [] and errors


def test_wildcard_identity_policy_is_not_presented_as_effective_full_administration():
    parsed = {
        "resources": {
            "aws_iam_role": {
                "reader": {
                    "inline_policy": [
                        {
                            "policy": {
                                "Statement": [
                                    {"Effect": "Allow", "Action": "*", "Resource": "*"}
                                ]
                            },
                        }
                    ],
                    "permissions_boundary": "${aws_iam_policy.boundary.arn}",
                }
            }
        }
    }
    [finding] = rule_iam_policy_wildcard_action_resource(parsed, "review")
    assert "wildcard" in finding.finding
    assert "full admin" not in finding.finding
    assert "permissions boundaries" in finding.risk_impact


@pytest.mark.parametrize("deep", [False, True])
def test_one_authoritative_dlq_number_survives_and_sibling_findings_are_not_lost(deep):
    [rule] = [
        f for f in run_rules(_queues(345600), "r1") if f.concern == "sqs_dlq_retention"
    ]
    record = rule.model_dump(mode="json")
    wrong = _valid_finding_item(
        finding="Dead-letter queue dead has inadequate retention.",
        recommendation="Set its message_retention_seconds to at least 86400.",
    )
    state = _reason_state([wrong, _valid_finding_item()], [] if deep else [record])
    if deep:
        state.update(deep_mode=True, parent_finding=record)
    result = reason_node(state)
    assert result["model_output_counts"] == {
        "attempted": 2,
        "accepted": 1,
        "rejected": 1,
    }
    if not deep:
        assert record["finding_id"] in [
            f["finding_id"] for f in result["reasoned_findings"]
        ]
        assert any(
            "432000 s" in f["recommendation"] for f in result["reasoned_findings"]
        )
    assert "dlq_retention_owned_by_rule" in result["dropped_model_findings"][0]
