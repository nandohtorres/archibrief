from dataclasses import asdict

import pytest

from backend.lambdas.ingest.handler import parse_terraform_files
from backend.lambdas.rule_engine.architecture import build_graph
from backend.lambdas.rule_engine.handler import run_rules
from backend.lambdas.rule_engine.resource_summary import build_resource_summary
from backend.shared.assessment import finding_assessment
from backend.shared.configuration_checks import configuration_issues
from tests.backend.adversarial.harness import FIXTURES
from tests.backend.lambdas.ingest.test_module_evaluation import parse
from tests.backend.shared.test_coverage_domains import bundle
from tests.backend.shared.test_terraform_observations import fact


def test_conditional_versioning_cannot_prove_the_bucket_is_versioned(tmp_path):
    parsed = parse(
        tmp_path,
        {
            "main.tf": """
variable "enabled" {}
resource "aws_s3_bucket" "b" {}
resource "aws_s3_bucket_versioning" "b" { count = var.enabled bucket = aws_s3_bucket.b.id versioning_configuration { status = "Enabled" } }
resource "aws_s3_bucket_lifecycle_configuration" "b" { bucket = aws_s3_bucket.b.id rule { status = "Enabled" filter {} expiration { days = 7 } } }
"""
        },
    )
    assert not any(
        issue.concern == "versioned_retention_gap"
        for issue in configuration_issues(build_resource_summary(parsed))
    )


@pytest.mark.parametrize(
    "resource_field,expected",
    [("resource_id = aws_api_gateway_resource.r.id", "known"), ("", "unknown")],
)
def test_backend_reference_requires_a_real_method_resource_link(
    tmp_path, resource_field, expected
):
    parsed = parse(
        tmp_path,
        {
            "main.tf": """
resource "aws_api_gateway_rest_api" "a" {}
resource "aws_api_gateway_resource" "r" {}
resource "aws_lambda_function" "f" {}
resource "aws_api_gateway_method" "m" { rest_api_id = aws_api_gateway_rest_api.a.id http_method = "POST" RESOURCE }
resource "aws_api_gateway_integration" "i" { rest_api_id = aws_api_gateway_rest_api.a.id http_method = "POST" RESOURCE uri = aws_lambda_function.f.invoke_arn }
""".replace("RESOURCE", resource_field)
        },
    )
    method = bundle(build_resource_summary(parsed), "aws_api_gateway_method", "m")
    assert fact(method, "lambda_backend_reference")["state"] == expected


def test_new_rules_find_real_fixture_defects_without_inventing_costs():
    for path, concern in (
        ("05_three_replicas_one_failure_domain/dangerous", "placement_single_az"),
        ("07_public_ai_api_cost_trap/dangerous", "invalid_sqs_mapping"),
        ("08_seven_day_deletion_fiction/dangerous", "versioned_retention_gap"),
    ):
        parsed = asdict(parse_terraform_files([str(FIXTURES / path / "main.tf")]))
        findings = [f for f in run_rules(parsed, "test") if f.concern == concern]
        assert findings, (path, concern)
        assert (
            finding_assessment(findings[0].model_dump(mode="json"))["action"]
            == "needed"
        )
        assert all(f.plain is None for f in findings)
        assert all("$" not in f.recommendation for f in findings)


def test_corrected_spread_az_fixture_is_not_flagged():
    parsed = asdict(
        parse_terraform_files(
            [str(FIXTURES / "05_three_replicas_one_failure_domain/corrected/main.tf")]
        )
    )
    assert not any(
        i.concern == "placement_single_az"
        for i in configuration_issues(build_resource_summary(parsed))
    )
    node = next(
        n
        for n in build_graph(parsed)["nodes"]
        if n["id"] == "aws_rds_cluster_instance.core"
    )
    assert any("us-east-1c" in detail for detail in node["details"])


@pytest.mark.parametrize(
    "extra",
    [
        "noncurrent_version_expiration { noncurrent_days = 1 }",
        'dynamic "noncurrent_version_expiration" { for_each = var.rules content { noncurrent_days = 1 } }',
    ],
)
def test_known_or_unknown_noncurrent_policy_does_not_become_an_absence(tmp_path, extra):
    parsed = parse(
        tmp_path,
        {
            "main.tf": """
variable "rules" {}
resource "aws_s3_bucket" "b" {}
resource "aws_s3_bucket_versioning" "b" { bucket = aws_s3_bucket.b.id versioning_configuration { status = "Enabled" } }
resource "aws_s3_bucket_lifecycle_configuration" "b" {
  bucket = aws_s3_bucket.b.id
  rule { status = "Enabled" filter {} expiration { days = 7 } EXTRA }
}
""".replace("EXTRA", extra)
        },
    )
    assert not any(
        i.concern == "versioned_retention_gap"
        for i in configuration_issues(build_resource_summary(parsed))
    )


@pytest.mark.parametrize(
    "visibility,expected", [(30, True), (300, False), (1800, False)]
)
def test_sqs_mapping_constraint_is_separate_from_retry_tuning(
    tmp_path, visibility, expected
):
    parsed = parse(
        tmp_path,
        {
            "main.tf": f"""
resource "aws_lambda_function" "f" {{ timeout = 300 }}
resource "aws_sqs_queue" "q" {{ visibility_timeout_seconds = {visibility} }}
resource "aws_lambda_event_source_mapping" "m" {{ function_name = aws_lambda_function.f.arn event_source_arn = aws_sqs_queue.q.arn }}
"""
        },
    )
    found = any(
        i.concern == "invalid_sqs_mapping"
        for i in configuration_issues(build_resource_summary(parsed))
    )
    assert found is expected


@pytest.mark.parametrize(
    "permissions,expected",
    [
        ("", "unknown"),
        (
            'resource "aws_lambda_permission" "u" { function_name = aws_lambda_function.f.function_name principal = "*" action = "lambda:InvokeFunctionUrl" function_url_auth_type = "NONE" }',
            "unknown",
        ),
        (
            """resource "aws_lambda_permission" "u" { function_name = aws_lambda_function.f.function_name principal = "*" action = "lambda:InvokeFunctionUrl" function_url_auth_type = "NONE" }
resource "aws_lambda_permission" "i" { function_name = aws_lambda_function.f.function_name principal = "*" action = "lambda:InvokeFunction" }""",
            "known",
        ),
    ],
)
def test_url_requires_both_declared_permission_actions(tmp_path, permissions, expected):
    parsed = parse(
        tmp_path,
        {
            "main.tf": """
resource "aws_lambda_function" "f" {}
resource "aws_lambda_function_url" "u" { function_name = aws_lambda_function.f.function_name authorization_type = "NONE" }
"""
            + permissions
        },
    )
    url = bundle(build_resource_summary(parsed), "aws_lambda_function_url", "u")
    assert fact(url, "public_invocation_permissions")["state"] == expected
    assert fact(url, "runtime_invocation")["state"] == "unknown"


@pytest.mark.parametrize(
    "target_kind,field",
    [
        ("aws_internet_gateway", "gateway_id"),
        ("aws_nat_gateway", "nat_gateway_id"),
        ("aws_egress_only_internet_gateway", "egress_only_gateway_id"),
    ],
)
def test_routing_target_kinds_do_not_collapse_to_public_reachability(
    tmp_path, target_kind, field
):
    parsed = parse(
        tmp_path,
        {
            "main.tf": f'''
resource "aws_vpc" "v" {{}}
resource "aws_subnet" "s" {{ vpc_id = aws_vpc.v.id }}
resource "{target_kind}" "g" {{ vpc_id = aws_vpc.v.id subnet_id = aws_subnet.s.id }}
resource "aws_route_table" "r" {{ vpc_id = aws_vpc.v.id route {{ ipv6_cidr_block = "::/0" {field} = {target_kind}.g.id }} }}
resource "aws_main_route_table_association" "m" {{ vpc_id = aws_vpc.v.id route_table_id = aws_route_table.r.id }}
'''
        },
    )
    subnet = bundle(build_resource_summary(parsed), "aws_subnet", "s")
    assert fact(subnet, "default_route.ipv6")["value"] == target_kind
    assert fact(subnet, "default_route.ipv4")["state"] == "unknown"
    assert fact(subnet, "runtime_reachability")["state"] == "unknown"
