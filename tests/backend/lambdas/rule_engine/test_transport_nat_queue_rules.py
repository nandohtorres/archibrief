"""Rules added 2026-10-30: database transport encryption, a single NAT
gateway, and a dead-letter queue that expires failures early."""

from pathlib import Path

import pytest

from backend.lambdas.ingest.handler import parse_terraform_files
from backend.lambdas.rule_engine.handler import (
    rule_rds_force_ssl_off,
    rule_single_nat_gateway,
    rule_sqs_dlq_retention,
)


def _parsed(tmp_path: Path, text: str) -> dict:
    path = tmp_path / "main.tf"
    path.write_text(text, encoding="utf-8")
    return vars(parse_terraform_files([str(path)]))


def _parameter_group(name: str, value: str, kind: str = "aws_rds_cluster_parameter_group") -> str:
    return f"""
resource "{kind}" "db" {{
  family = "aurora-postgresql15"
  parameter {{
    name  = "{name}"
    value = "{value}"
  }}
}}
"""


@pytest.mark.parametrize(
    ("name", "value", "kind"),
    [
        ("rds.force_ssl", "0", "aws_rds_cluster_parameter_group"),
        ("rds.force_ssl", "0", "aws_db_parameter_group"),
        ("require_secure_transport", "OFF", "aws_db_parameter_group"),
    ],
)
def test_a_parameter_that_turns_tls_off_is_found(tmp_path, name, value, kind):
    findings = rule_rds_force_ssl_off(_parsed(tmp_path, _parameter_group(name, value, kind)), "r")
    assert [f.finding for f in findings] == [
        "Database parameter group 'db' allows unencrypted connections"
    ]
    assert f"{name} = {value}" in findings[0].evidence


@pytest.mark.parametrize(
    ("name", "value"),
    [("rds.force_ssl", "1"), ("require_secure_transport", "ON"), ("log_statement", "0")],
)
def test_tls_on_or_another_parameter_is_not_a_finding(tmp_path, name, value):
    assert rule_rds_force_ssl_off(_parsed(tmp_path, _parameter_group(name, value)), "r") == []


def test_force_ssl_off_through_a_variable_is_found(tmp_path):
    text = """
variable "force_ssl" {
  default = "0"
}
resource "aws_db_parameter_group" "db" {
  family = "postgres16"
  parameter {
    name  = "rds.force_ssl"
    value = var.force_ssl
  }
}
"""
    assert len(rule_rds_force_ssl_off(_parsed(tmp_path, text), "r")) == 1


_SUBNETS = """
resource "aws_subnet" "private" {
  count = 3
}
"""


def test_one_nat_gateway_for_several_subnets_is_found(tmp_path):
    text = _SUBNETS + 'resource "aws_nat_gateway" "main" {}\n'
    findings = rule_single_nat_gateway(_parsed(tmp_path, text), "r")
    assert [f.finding for f in findings] == ["NAT gateway 'main' is the only one for 3 subnets"]


@pytest.mark.parametrize(
    "nat",
    [
        'resource "aws_nat_gateway" "main" {\n  count = 3\n}\n',
        'resource "aws_nat_gateway" "a" {}\nresource "aws_nat_gateway" "b" {}\n',
        # A count the rule can't read is skipped, not guessed.
        'resource "aws_nat_gateway" "main" {\n  count = length(data.aws_availability_zones.x.names)\n}\n',
        "",
    ],
    ids=["counted", "two", "unknown-count", "none"],
)
def test_a_nat_per_zone_an_unknown_count_or_no_nat_is_not_a_finding(tmp_path, nat):
    assert rule_single_nat_gateway(_parsed(tmp_path, _SUBNETS + nat), "r") == []


def test_one_nat_gateway_for_one_subnet_is_not_a_finding(tmp_path):
    text = 'resource "aws_subnet" "only" {}\nresource "aws_nat_gateway" "main" {}\n'
    assert rule_single_nat_gateway(_parsed(tmp_path, text), "r") == []


def _queues(dlq_retention: str | None, source_retention: str | None, extra: str = "") -> str:
    dlq = f"  message_retention_seconds = {dlq_retention}\n" if dlq_retention else ""
    source = f"  message_retention_seconds = {source_retention}\n" if source_retention else ""
    return f"""
resource "aws_sqs_queue" "jobs_dlq" {{
{dlq}{extra}}}
resource "aws_sqs_queue" "jobs" {{
{source}{extra}  redrive_policy = jsonencode({{
    deadLetterTargetArn = aws_sqs_queue.jobs_dlq.arn
    maxReceiveCount     = 3
  }})
}}
"""


def test_a_dead_letter_queue_that_keeps_messages_less_time_is_found(tmp_path):
    findings = rule_sqs_dlq_retention(_parsed(tmp_path, _queues("345600", "1209600")), "r")
    assert [f.finding for f in findings] == [
        "Dead-letter queue 'jobs_dlq' keeps messages for less time than queue 'jobs'"
    ]
    assert "1209600 s" in findings[0].evidence and "345600 s" in findings[0].evidence


def test_an_unset_dead_letter_retention_uses_the_four_day_default(tmp_path):
    assert len(rule_sqs_dlq_retention(_parsed(tmp_path, _queues(None, "1209600")), "r")) == 1


@pytest.mark.parametrize(
    ("dlq", "source", "extra"),
    [
        ("1209600", "345600", ""),
        (None, None, ""),
        ("345600", "var.unknown", ""),
        ("345600", "1209600", "  fifo_queue = true\n"),
    ],
    ids=["longer", "both-default", "unknown", "fifo"],
)
def test_longer_equal_unknown_or_fifo_retention_is_not_a_finding(tmp_path, dlq, source, extra):
    assert rule_sqs_dlq_retention(_parsed(tmp_path, _queues(dlq, source, extra)), "r") == []


def test_a_standalone_redrive_policy_is_checked_too(tmp_path):
    text = """
resource "aws_sqs_queue" "jobs_dlq" {}
resource "aws_sqs_queue" "jobs" {
  message_retention_seconds = 1209600
}
resource "aws_sqs_queue_redrive_policy" "jobs" {
  queue_url = aws_sqs_queue.jobs.id
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.jobs_dlq.arn
    maxReceiveCount     = 3
  })
}
"""
    assert len(rule_sqs_dlq_retention(_parsed(tmp_path, text), "r")) == 1
