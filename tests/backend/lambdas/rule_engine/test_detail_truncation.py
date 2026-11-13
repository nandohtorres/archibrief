"""Nested-detail limits must preserve obvious risks and disclose every omission."""

import json
from copy import deepcopy
from dataclasses import asdict

import pytest

from backend.agent.nodes.reason import _resources_for_model
from backend.lambdas.ingest.handler import parse_terraform_files
from backend.lambdas.rule_engine.resource_summary import build_resource_summary
from backend.shared.analysis_quality import public_analysis_scope

# Each case places the decisive fact after the old ten-item cutoff.
CASES = [
    (
        "aws_security_group",
        "ingress",
        "ingress",
        {
            "protocol": "tcp",
            "from_port": 443,
            "to_port": 443,
            "cidr_blocks": ["10.0.0.0/8"],
        },
        {"protocol": "-1", "cidr_blocks": ["0.0.0.0/0"]},
        "source",
        "internet (0.0.0.0/0 or ::/0)",
    ),
    (
        "aws_iam_policy",
        "policy",
        "statements",
        {
            "Effect": "Allow",
            "Action": "logs:DescribeLogGroups",
            "Resource": "arn:aws:logs:us-east-1:123456789012:log-group:app",
        },
        {"Effect": "Allow", "Action": "*", "Resource": "*"},
        "sensitive_actions",
        ["* (every action)"],
    ),
    (
        "aws_iam_role",
        "assume_role_policy",
        "trust",
        {
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole",
        },
        {"Effect": "Allow", "Principal": "*", "Action": "sts:AssumeRole"},
        "trusted",
        "anyone (*)",
    ),
    (
        "aws_cloudfront_distribution",
        "origin",
        "origins",
        {"custom_origin_config": [{"origin_protocol_policy": "https-only"}]},
        {"custom_origin_config": [{"origin_protocol_policy": "http-only"}]},
        "connection_to_origin",
        "http-only",
    ),
    (
        "aws_cloudfront_distribution",
        "ordered_cache_behavior",
        "other_behaviors_viewer_protocol",
        {"viewer_protocol_policy": "https-only"},
        {"viewer_protocol_policy": "allow-all"},
        None,
        "allow-all",
    ),
    (
        "aws_ecs_task_definition",
        "container_definitions",
        "containers",
        {"image": "example:v1", "privileged": False, "readonlyRootFilesystem": True},
        {"image": "example:latest", "privileged": True},
        "privileged",
        True,
    ),
    (
        "aws_backup_plan",
        "rule",
        "rules",
        {"lifecycle": [{"delete_after": 35}]},
        {"lifecycle": [{"delete_after": 1}], "copy_action": [{}]},
        "delete_after_days",
        1,
    ),
]


def _body(attribute, items):
    value = (
        {"Statement": items} if attribute in {"policy", "assume_role_policy"} else items
    )
    return {attribute: value}


@pytest.mark.parametrize("case", CASES, ids=[case[2] for case in CASES])
@pytest.mark.parametrize("total", [0, 10, 11, 23])
def test_every_bounded_collection_discloses_omissions_and_keeps_risk(case, total):
    kind, attribute, collection, benign, risky, field, expected = case
    items = [deepcopy(benign) for _ in range(max(0, total - 1))]
    if total:
        items.append(deepcopy(risky))
    parsed = {"resources": {kind: {"example": _body(attribute, items)}}}
    before = deepcopy(parsed)
    summary = build_resource_summary(parsed)
    entry = summary["resources"][0]
    details = entry if kind == "aws_backup_plan" else entry.get("details", {})
    if not total and attribute in {"policy", "assume_role_policy"}:
        # Empty documents already produce no detail collection.
        assert collection not in details
    else:
        assert len(details[collection]) == min(10, total)
        assert details[f"{collection}_total"] == total
        assert details[f"{collection}_omitted"] == max(0, total - 10)
        if total:
            # Below the bound the existing source order stays unchanged.
            risk = details[collection][0 if total > 10 else -1]
            assert (risk[field] if field else risk) == expected
    coverage = summary["analysis_coverage"]
    assert coverage["detail_omitted_items"] == max(0, total - 10)
    assert coverage["omitted_items"] >= coverage["detail_omitted_items"]
    assert coverage["truncated"] is (total > 10)
    assert public_analysis_scope(coverage)["truncated"] is (total > 10)
    assert _resources_for_model(summary)["resources"][0].get("details") == entry.get(
        "details"
    )
    assert parsed == before


@pytest.mark.parametrize("principal", ["*", {"AWS": "*"}, {"AWS": ["*"]}])
def test_ten_benign_then_wildcard_trust_reaches_model_with_gap(tmp_path, principal):
    statements = [
        {
            "Effect": "Allow",
            "Action": "sts:AssumeRole",
            "Principal": {"Service": "lambda.amazonaws.com"},
        }
        for _ in range(10)
    ]
    statements.append(
        {"Effect": "Allow", "Action": "sts:AssumeRole", "Principal": principal}
    )
    source = tmp_path / "main.tf"
    source.write_text(
        'provider "aws" { region = "us-east-1" }\n'
        'resource "aws_iam_role" "example" {\nassume_role_policy = <<POLICY\n'
        + json.dumps({"Statement": statements})
        + "\nPOLICY\n}\n",
        encoding="utf-8",
    )
    parsed = asdict(parse_terraform_files([str(source)]))
    model = _resources_for_model(build_resource_summary(parsed))
    details = model["resources"][0]["details"]
    assert details["trust"][0]["trusted"] == "anyone (*)"
    assert len(details["trust"]) == 10
    assert details["trust_total"] == 11
    assert details["trust_omitted"] == 1
    coverage = model["analysis_coverage"]
    assert coverage["placement_only_resources"] == 1
    assert coverage["omitted_resources"] == 0
    assert coverage["omitted_items"] == 1
    assert coverage["truncated"] is True
    assert model["truncated"] is False  # All resource entries are present.


def test_inline_policies_and_multiple_collections_add_to_existing_observation_gaps(
    monkeypatch,
):
    from backend.lambdas.rule_engine.resource_summary import ResourceObservations

    original = ResourceObservations.build

    def with_observation_gap(self):
        bundle = original(self)
        bundle.update(omitted_items=2, truncated=True)
        return bundle

    monkeypatch.setattr(ResourceObservations, "build", with_observation_gap)
    policy = {"Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}] * 13}
    parsed = {
        "resources": {
            "aws_iam_role": {
                "role": {
                    "assume_role_policy": {
                        "Statement": [{"Effect": "Allow", "Principal": "*"}] * 11
                    },
                    "inline_policy": [{"policy": policy}, {"policy": policy}],
                }
            },
            "aws_cloudfront_distribution": {
                "cdn": {
                    "origin": [{"origin_access_control_id": "oac"}] * 12,
                    "ordered_cache_behavior": [{"viewer_protocol_policy": "allow-all"}]
                    * 14,
                }
            },
        }
    }
    coverage = build_resource_summary(parsed)["analysis_coverage"]
    assert coverage["detail_omitted_items"] == 1 + 3 + 3 + 2 + 4
    assert coverage["omitted_items"] == 17  # Plus two observation gaps per resource.
    assert public_analysis_scope(coverage)["omitted_items"] == 17


def test_observation_budget_rejection_does_not_hide_detail_gap(monkeypatch):
    monkeypatch.setattr("backend.shared.terraform_observations.MAX_BYTES", 0)
    parsed = {
        "resources": {
            "aws_iam_policy": {
                "policy": {
                    "policy": {
                        "Statement": [
                            {"Effect": "Allow", "Action": "*", "Resource": "*"}
                        ]
                        * 11
                    },
                }
            }
        }
    }
    summary = build_resource_summary(parsed)
    assert "observations" not in summary["resources"][0]
    assert summary["analysis_coverage"]["omitted_resources"] == 1
    assert summary["analysis_coverage"]["omitted_items"] == 1
    assert summary["analysis_coverage"]["truncated"] is True


def test_risk_ties_are_stable_and_deny_is_not_rewritten_as_allow():
    statements = [{"Effect": "Deny", "Action": "*", "Resource": "*"}]
    statements += [{"Effect": "Allow", "Action": "logs:DescribeLogGroups"}] * 9
    statements += [
        {"Effect": "Allow", "Action": action, "Resource": "*"}
        for action in ["iam:PassRole", "iam:CreateRole"]
    ]
    summary = build_resource_summary(
        {
            "resources": {
                "aws_iam_policy": {
                    "policy": {
                        "policy": {"Statement": statements},
                    }
                }
            }
        }
    )
    details = summary["resources"][0]["details"]
    assert [s["sensitive_actions"] for s in details["statements"][:2]] == [
        ["iam:PassRole"],
        ["iam:CreateRole"],
    ]
    assert details["statements"][2]["effect"] == "Deny"
    assert details["statements_omitted"] == 2


@pytest.mark.parametrize(
    "case_index,risky,field,expected",
    [
        (
            1,
            {"Effect": "Allow", "NotAction": "iam:DeleteUser", "Resource": "*"},
            "actions",
            "every action except those listed (NotAction)",
        ),
        (
            2,
            {"Effect": "Allow", "Principal": {"AWS": "123456789012"}},
            "trusted",
            ["a whole AWS account by ID (any role or user that account allows)"],
        ),
        (
            2,
            {
                "Effect": "Allow",
                "Principal": {"Federated": "token.actions.githubusercontent.com"},
                "Condition": {
                    "StringLike": {
                        "token.actions.githubusercontent.com:sub": "repo:example/*"
                    }
                },
            },
            "github_subject_admits",
            "any repository in the organization (wildcard)",
        ),
        (
            5,
            {
                "image": "example:v1",
                "readonlyRootFilesystem": True,
                "environment": [
                    {"name": "API_TOKEN", "value": "never-copy-this-secret"}
                ],
            },
            "environment",
            {
                "variables": 1,
                "secret_like_names_with_literal_values": 1,
                "secret_like_names_from_references": 0,
            },
        ),
    ],
)
def test_other_decisive_risks_beyond_the_bound_are_retained(
    case_index, risky, field, expected
):
    kind, attribute, collection, benign, *_ = CASES[case_index]
    summary = build_resource_summary(
        {
            "resources": {
                kind: {
                    "example": _body(
                        attribute, [deepcopy(benign) for _ in range(10)] + [risky]
                    ),
                }
            }
        }
    )
    details = summary["resources"][0]["details"]
    assert details[collection][0][field] == expected
    assert details[f"{collection}_omitted"] == 1
    assert summary["analysis_coverage"]["truncated"] is True
    assert "never-copy-this-secret" not in json.dumps(_resources_for_model(summary))


@pytest.mark.parametrize(
    "kind,attribute,collection",
    [
        ("aws_cloudfront_distribution", "origin", "origins"),
        ("aws_ecs_task_definition", "container_definitions", "containers"),
    ],
)
def test_skipped_malformed_items_are_also_disclosed(kind, attribute, collection):
    summary = build_resource_summary(
        {
            "resources": {
                kind: {
                    "example": {
                        attribute: [None, {}],
                    }
                }
            }
        }
    )
    details = summary["resources"][0]["details"]
    assert details[f"{collection}_total"] == 2
    assert len(details[collection]) == 1
    assert details[f"{collection}_omitted"] == 1
    assert summary["analysis_coverage"]["truncated"] is True
