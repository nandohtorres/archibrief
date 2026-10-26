import json
from dataclasses import asdict

from backend.lambdas.ingest.handler import parse_terraform_files
from backend.lambdas.rule_engine.resource_summary import build_resource_summary
from backend.shared import terraform_observations as observations
from tests.backend.adversarial.harness import FIXTURES
from tests.backend.lambdas.ingest.test_module_evaluation import parse
from tests.backend.shared.test_terraform_observations import fact


def fixture_summary(path):
    parsed = asdict(parse_terraform_files([str(FIXTURES / path / "main.tf")]))
    return build_resource_summary(parsed)


def bundle(summary, kind, name):
    return next(
        e["observations"]
        for e in summary["resources"]
        if e["type"] == kind and e["name"] == name
    )


def test_f05_counts_and_element_list_preserve_same_and_spread_azs():
    for variant, expected in (
        ("dangerous", {"us-east-1a"}),
        ("corrected", {"us-east-1a", "us-east-1b", "us-east-1c"}),
    ):
        summary = fixture_summary(f"05_three_replicas_one_failure_domain/{variant}")
        core = bundle(summary, "aws_rds_cluster_instance", "core")
        azs = {
            f["value"]
            for f in core["facts"]
            if f["setting"].startswith("availability_zone[")
        }
        assert azs == expected
        assert (
            len(
                [
                    f
                    for f in core["facts"]
                    if f["setting"].startswith("availability_zone[")
                ]
            )
            == 3
        )


def test_f06_native_retention_selection_and_last_copy_remain_distinct():
    summary = fixture_summary("06_backup_plan_without_protection/dangerous")
    native = bundle(summary, "aws_db_instance", "prod_ledger")
    assert fact(native, "backup_retention_period")["value"] == 7
    selection = bundle(summary, "aws_backup_selection", "dev_only")
    assert any(
        r["target"] == "aws_db_instance.dev_sandbox" and r["setting"] == "resources[0]"
        for r in selection["relations"]
    )
    assert not any(
        r["target"] == "aws_db_instance.prod_ledger" for r in selection["relations"]
    )
    plan = bundle(summary, "aws_backup_plan", "nightly")
    assert fact(plan, "rule[10].source_retention_days")["value"] == 1
    assert fact(plan, "rule[10].copy[0].explicit_retention_days")["state"] == "absent"
    assert fact(plan, "rule[10].copy[0].derived_retention_days")["value"] == 1


def test_f07_auth_and_linkage_do_not_invent_invocation():
    summary = fixture_summary("07_public_ai_api_cost_trap/dangerous")
    url = bundle(summary, "aws_lambda_function_url", "inference_direct")
    assert fact(url, "authorization_type")["value"] == "NONE"
    assert fact(url, "runtime_invocation")["state"] == "unknown"
    mapping = bundle(summary, "aws_lambda_event_source_mapping", "jobs")
    assert {r["target"] for r in mapping["relations"]} == {
        "aws_sqs_queue.jobs",
        "aws_lambda_function.inference",
    }
    method = bundle(summary, "aws_api_gateway_method", "post_batch")
    assert fact(method, "authorization")["value"] == "NONE"
    assert fact(method, "runtime_invocation")["state"] == "unknown"


def test_f08_independent_lifecycles_and_unknown_ttl_writer():
    summary = fixture_summary("08_seven_day_deletion_fiction/dangerous")
    for name in ("uploads", "uploads_replica"):
        lifecycle = bundle(summary, "aws_s3_bucket_lifecycle_configuration", name)
        assert fact(lifecycle, "rule[0].expiration.days")["value"] == 7
        assert (
            fact(lifecycle, "rule[0].noncurrent_version_expiration.noncurrent_days")[
                "state"
            ]
            == "absent"
        )
        assert fact(lifecycle, "rule[0].filter_scope")["value"] == "all_objects"
        assert any(
            r["target"] == f"aws_s3_bucket.{name}" for r in lifecycle["relations"]
        )
    ttl = bundle(summary, "aws_dynamodb_table", "sessions")
    assert fact(ttl, "ttl.enabled")["value"] is True
    assert fact(ttl, "ttl.writer")["state"] == "unknown"


def test_f04_route_association_and_target_kind_are_explicit():
    summary = fixture_summary("04_private_subnet_public_path/dangerous")
    route = bundle(summary, "aws_route_table", "public_rt")
    assert fact(route, "route[0].cidr_block")["value"] == "0.0.0.0/0"
    assert any(r["target"] == "aws_internet_gateway.igw" for r in route["relations"])
    association = bundle(summary, "aws_route_table_association", "db_a")
    assert {r["target"] for r in association["relations"]} == {
        "aws_subnet.private_db_a",
        "aws_route_table.public_rt",
    }


def test_unsupported_dynamic_blocks_and_nested_expressions_are_unknown(tmp_path):
    parsed = parse(
        tmp_path,
        {
            "main.tf": """
variable "rules" {}
resource "aws_dynamodb_table" "d" {
  dynamic "ttl" { for_each = var.rules content { enabled = true } }
}
resource "aws_s3_bucket_lifecycle_configuration" "l" {
  dynamic "rule" { for_each = var.rules content { status = "Enabled" } }
}
"""
        },
    )
    summary = build_resource_summary(parsed)
    assert (
        fact(bundle(summary, "aws_dynamodb_table", "d"), "ttl.enabled")["state"]
        == "unknown"
    )
    assert (
        fact(bundle(summary, "aws_s3_bucket_lifecycle_configuration", "l"), "rule")[
            "state"
        ]
        == "unsupported"
    )


def test_observation_budget_discloses_omission_without_reporting_absence(
    tmp_path, monkeypatch
):
    parsed = parse(
        tmp_path,
        {
            "main.tf": "\n".join(
                f'resource "aws_instance" "i{n}" {{}}' for n in range(10)
            )
        },
    )
    monkeypatch.setattr(observations, "MAX_BYTES", 1800)
    summary = build_resource_summary(parsed)
    manifest = summary["analysis_coverage"]
    assert manifest["truncated"] is True
    assert manifest["omitted_resources"] > 0
    assert manifest["emitted_bytes"] <= 1800
    assert len(summary["resources"]) == 10
    assert summary["truncated"] is False


def test_resource_region_override_is_not_confused_with_provider_region(tmp_path):
    parsed = parse(
        tmp_path,
        {
            "main.tf": """
provider "aws" { region = "us-east-1" }
resource "aws_instance" "west" { region = "us-west-2" }
"""
        },
    )
    observed = bundle(build_resource_summary(parsed), "aws_instance", "west")
    assert fact(observed, "provider.region")["value"] == "us-east-1"
    assert fact(observed, "resource.region")["value"] == "us-west-2"
    assert "PRIVATE-CANARY" not in json.dumps(observed)


def test_bounded_exact_tag_selection_keeps_unknown_tags_and_raw_text_private(tmp_path):
    parsed = parse(
        tmp_path,
        {
            "main.tf": """
resource "aws_backup_plan" "p" {}
resource "aws_db_instance" "prod" { tags = { env = "prod" } }
resource "aws_db_instance" "dev" { tags = { env = "dev" } }
resource "aws_db_instance" "unknown" {}
resource "aws_backup_selection" "s" {
  plan_id = aws_backup_plan.p.id
  selection_tag { type = "STRINGEQUALS" key = "env" value = "prod" }
}
"""
        },
    )
    selected = bundle(build_resource_summary(parsed), "aws_backup_selection", "s")
    links = {
        r["target"]: r
        for r in selected["relations"]
        if r["setting"] == "tag_selector_match"
    }
    assert links["aws_db_instance.prod"]["matches_selector"] is True
    assert links["aws_db_instance.dev"]["matches_selector"] is False
    assert links["aws_db_instance.unknown"]["state"] == "unknown"
    assert fact(selected, "tag_selection")["value"] == "bounded_exact_predicates"


def test_unexpanded_dynamic_rule_prevents_a_false_retention_claim(tmp_path):
    from backend.shared.configuration_checks import configuration_issues

    parsed = parse(
        tmp_path,
        {
            "main.tf": """
variable "rules" {}
resource "aws_s3_bucket" "b" {}
resource "aws_s3_bucket_versioning" "b" { bucket = aws_s3_bucket.b.id versioning_configuration { status = "Enabled" } }
resource "aws_s3_bucket_lifecycle_configuration" "b" {
 bucket = aws_s3_bucket.b.id
 rule { status = "Enabled" expiration { days = 7 } filter {} }
 dynamic "rule" { for_each = var.rules content { status = "Enabled" noncurrent_version_expiration { noncurrent_days = 1 } } }
}
"""
        },
    )
    assert not any(
        issue.concern == "versioned_retention_gap"
        for issue in configuration_issues(build_resource_summary(parsed))
    )
