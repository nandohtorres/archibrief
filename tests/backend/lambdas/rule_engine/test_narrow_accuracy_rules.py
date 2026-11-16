"""Synthetic declared-configuration cases; no evaluation cases or credentials."""

import json

import pytest

from backend.lambdas.rule_engine.handler import run_rules
from backend.shared.assessment import finding_assessment


def check(kind, body, concern, extra=None):
    resources = {kind: {"subject": body}, **(extra or {})}
    return [
        f
        for f in run_rules({"resources": resources}, "synthetic-rules")
        if f.concern == concern
    ]


@pytest.mark.parametrize(
    "route,authorization,expected",
    [
        ("GET /orders", "NONE", True),
        ("$default", "NONE", True),
        ("GET /health", "NONE", False),
        ("GET /healthz/", "NONE", False),
        ("GET /status", "NONE", False),
        ("GET /health/private", "NONE", True),
        ("GET /orders", "JWT", False),
        ("GET /orders", "AWS_IAM", False),
        ("GET /orders", "${var.auth}", False),
        ("GET /orders", None, False),
        ("${var.route}", "NONE", False),
    ],
)
def test_api_route(route, authorization, expected):
    findings = check(
        "aws_apigatewayv2_route",
        {"route_key": route, "authorization_type": authorization},
        "api_route_no_authorization",
    )
    assert bool(findings) is expected
    if expected:
        assert (
            finding_assessment(findings[0].model_dump(mode="json"))["severity"]
            == "high"
        )
        assert "Confirm this route is meant to be public" in findings[0].recommendation


@pytest.mark.parametrize(
    "path,authorization,expected",
    [("orders", "NONE", True), ("health", "NONE", False), ("orders", "AWS_IAM", False)],
)
def test_rest_method_path(path, authorization, expected):
    extra = {
        "aws_api_gateway_resource": {
            "path": {
                "path_part": path,
                "parent_id": "${aws_api_gateway_rest_api.api.root_resource_id}",
            }
        }
    }
    assert (
        bool(
            check(
                "aws_api_gateway_method",
                {
                    "authorization": authorization,
                    "resource_id": "${aws_api_gateway_resource.path.id}",
                },
                "api_route_no_authorization",
                extra,
            )
        )
        is expected
    )


@pytest.mark.parametrize(
    "kind,action",
    [
        ("aws_sqs_queue_policy", "sqs:SendMessage"),
        ("aws_sns_topic_policy", "sns:Publish"),
    ],
)
@pytest.mark.parametrize(
    "principal,action_override,effect,condition,expected",
    [
        ("*", None, "Allow", None, True),
        ({"AWS": "*"}, "*", "Allow", {}, True),
        ("*", None, "Deny", None, False),
        ("arn:aws:iam::123456789012:root", None, "Allow", None, False),
        ("*", "sqs:ReceiveMessage", "Allow", None, False),
        ("*", None, "Allow", {"ArnEquals": {"aws:SourceArn": "source"}}, False),
        ("*", None, "Allow", "${var.condition}", False),
    ],
)
def test_messaging(
    kind, action, principal, action_override, effect, condition, expected
):
    statement = {
        "Principal": principal,
        "Action": [action_override or action],
        "Effect": effect,
        "Resource": "*",
    }
    if condition is not None:
        statement["Condition"] = condition
    assert (
        bool(
            check(
                kind,
                {"policy": json.dumps({"Statement": [statement]})},
                "messaging_public_publish",
            )
        )
        is expected
    )


@pytest.mark.parametrize("target", ["role", "user", "group"])
@pytest.mark.parametrize(
    "arn,expected",
    [
        ("arn:aws:iam::aws:policy/AdministratorAccess", True),
        ("arn:aws-us-gov:iam::aws:policy/AdministratorAccess", True),
        ("arn:aws-cn:iam::aws:policy/AdministratorAccess", True),
        ("arn:aws:iam::aws:policy/ReadOnlyAccess", False),
        ("arn:aws:iam::123456789012:policy/AdministratorAccess", False),
        ("arn:aws:iam::aws:policy/job-function/AdministratorAccess", False),
        ("${var.policy}", False),
    ],
)
def test_administrator_attachments(target, arn, expected):
    findings = check(
        f"aws_iam_{target}_policy_attachment",
        {"policy_arn": arn, target: "principal"},
        "iam_administrator_access_attachment",
    )
    assert bool(findings) is expected
    if findings:
        assert "boundaries" in findings[0].risk_impact


@pytest.mark.parametrize("block", ["default_cache_behavior", "ordered_cache_behavior"])
@pytest.mark.parametrize(
    "policy,expected",
    [
        ("allow-all", True),
        ("redirect-to-https", False),
        ("https-only", False),
        ("${var.policy}", False),
        (None, False),
    ],
)
def test_cloudfront(block, policy, expected):
    assert (
        bool(
            check(
                "aws_cloudfront_distribution",
                {block: [{"viewer_protocol_policy": policy}]},
                "cloudfront_plain_http",
            )
        )
        is expected
    )


@pytest.mark.parametrize(
    "kind,field",
    [("aws_db_instance", "password"), ("aws_rds_cluster", "master_password")],
)
@pytest.mark.parametrize(
    "value,expected",
    [
        ("synthetic-test-value", True),
        ("", False),
        (None, False),
        ("${var.password}", False),
        ("${data.aws_secretsmanager_secret_version.db.secret_string}", False),
        ("${random_password.db.result}", False),
        ("${local.password}", False),
        ("prefix-${var.password}", False),
        ("var.password", False),
    ],
)
def test_literal_password_never_echoed(kind, field, value, expected):
    findings = check(kind, {field: value}, "database_literal_password")
    assert bool(findings) is expected
    if findings:
        assert value not in json.dumps([f.model_dump(mode="json") for f in findings])


@pytest.mark.parametrize("managed", [True, "${var.managed}"])
def test_managed_password_is_excluded(managed):
    assert not check(
        "aws_db_instance",
        {"password": "synthetic-test-value", "manage_master_user_password": managed},
        "database_literal_password",
    )


@pytest.mark.parametrize(
    "kind,body,concern",
    [
        (
            "aws_apigatewayv2_route",
            {"route_key": "GET /orders", "authorization_type": "NONE"},
            "api_route_no_authorization",
        ),
        (
            "aws_db_instance",
            {"password": "synthetic-test-value"},
            "database_literal_password",
        ),
        (
            "aws_cloudfront_distribution",
            {"default_cache_behavior": [{"viewer_protocol_policy": "allow-all"}]},
            "cloudfront_plain_http",
        ),
    ],
)
def test_disabled_resources_do_not_fire(kind, body, concern):
    assert not check(kind, {**body, "count": 0}, concern)


def test_rest_root_without_authorization_is_not_a_health_path():
    assert check(
        "aws_api_gateway_method",
        {
            "authorization": "NONE",
            "resource_id": "${aws_api_gateway_rest_api.api.root_resource_id}",
        },
        "api_route_no_authorization",
    )


def test_nested_rest_health_path_does_not_exempt_private_child():
    extra = {
        "aws_api_gateway_resource": {
            "health": {
                "path_part": "health",
                "parent_id": "${aws_api_gateway_rest_api.api.root_resource_id}",
            },
            "child": {
                "path_part": "private",
                "parent_id": "${aws_api_gateway_resource.health.id}",
            },
        }
    }
    assert check(
        "aws_api_gateway_method",
        {
            "authorization": "NONE",
            "resource_id": "${aws_api_gateway_resource.child.id}",
        },
        "api_route_no_authorization",
        extra,
    )


def test_api_with_unresolved_rest_path_is_not_guessed():
    assert not check(
        "aws_api_gateway_method",
        {"authorization": "NONE", "resource_id": "${var.resource_id}"},
        "api_route_no_authorization",
    )


def test_literal_password_with_explicit_managed_mode_off():
    assert check(
        "aws_db_instance",
        {"password": "synthetic-test-value", "manage_master_user_password": False},
        "database_literal_password",
    )


def test_new_rule_versions_and_assessments_are_explicit():
    finding = check(
        "aws_cloudfront_distribution",
        {"ordered_cache_behavior": [{"viewer_protocol_policy": "allow-all"}]},
        "cloudfront_plain_http",
    )[0]
    assert finding.deterministic_rule_version == "rule_engine@2026-11-16a"
    assert finding_assessment(finding.model_dump(mode="json"))["severity"] == "medium"
