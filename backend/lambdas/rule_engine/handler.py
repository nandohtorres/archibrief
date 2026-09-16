"""ArchiBrief Lambda: rule-engine.

Deterministic checks against the parsed Terraform resource tree (IAM,
exposure, encryption, availability, recovery, observability, cost — the
v1 scenario list in Work-Project-Spec.md). Every check produces zero or
more `Finding` objects of type deterministic-rule-result — never a raw
dict (Work-Project-Coding-Conventions.md "Typed-finding discipline").
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Iterable

from backend.shared.models.finding import (
    ConfidenceInputs,
    Finding,
    FindingCategory,
    FindingType,
)

RULE_VERSION = "rule_engine@2026-09-08"

SENSITIVE_PORTS = {22, 3389, 3306, 5432, 1433, 6379, 9200, 27017}


def _finding(
    review_id: str,
    category: FindingCategory,
    text: str,
    evidence: str,
    risk_impact: str,
    recommendation: str,
    framework_mapping: list[str],
) -> Finding:
    return Finding(
        finding_id=str(uuid.uuid4()),
        review_id=review_id,
        category=category,
        type=FindingType.DETERMINISTIC_RULE_RESULT,
        finding=text,
        evidence=evidence,
        citation=None,
        confidence=1.0,
        confidence_inputs=ConfidenceInputs(
            evidence_directness=1.0, source_agreement=1.0, rule_determinism=1.0
        ),
        risk_impact=risk_impact,
        recommendation=recommendation,
        framework_mapping=framework_mapping,
        depth_level="lightweight",
        deterministic_rule_version=RULE_VERSION,
    )


def _resources(parsed: dict, resource_type: str) -> Iterable[tuple[str, dict]]:
    return parsed.get("resources", {}).get(resource_type, {}).items()


def _bucket_names_referenced_by(companion_resources: Iterable[tuple[str, dict]]) -> set[str]:
    """Extract which aws_s3_bucket local names a companion resource's `bucket`
    attribute points at — handles both `aws_s3_bucket.<name>.id` interpolation
    references and (less idiomatically) a literal bucket name reused directly.
    """
    referenced: set[str] = set()
    for _, body in companion_resources:
        value = body.get("bucket")
        if not isinstance(value, str):
            continue
        match = re.search(r"aws_s3_bucket\.([A-Za-z0-9_-]+)", value)
        if match:
            referenced.add(match.group(1))
        else:
            referenced.add(value)
    return referenced


def rule_s3_public_access_block(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    buckets = dict(_resources(parsed, "aws_s3_bucket"))
    blocked = _bucket_names_referenced_by(_resources(parsed, "aws_s3_bucket_public_access_block"))
    for name in buckets:
        if name not in blocked:
            findings.append(
                _finding(
                    review_id,
                    FindingCategory.EXPOSURE,
                    f"S3 bucket '{name}' has no aws_s3_bucket_public_access_block resource",
                    f'resource "aws_s3_bucket" "{name}" found with no matching public access block',
                    "Bucket contents may be exposed publicly if a future ACL/policy change is misconfigured.",
                    "Attach aws_s3_bucket_public_access_block with all four settings enabled.",
                    ["AWS Well-Architected: Security Pillar"],
                )
            )
    return findings


def rule_s3_encryption(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    buckets = dict(_resources(parsed, "aws_s3_bucket"))
    encrypted = _bucket_names_referenced_by(
        _resources(parsed, "aws_s3_bucket_server_side_encryption_configuration")
    )
    for name in buckets:
        if name not in encrypted:
            findings.append(
                _finding(
                    review_id,
                    FindingCategory.ENCRYPTION,
                    f"S3 bucket '{name}' has no server-side encryption configuration",
                    f'resource "aws_s3_bucket" "{name}" found with no matching SSE configuration',
                    "Data at rest is unencrypted, violating baseline data-protection expectations.",
                    "Attach aws_s3_bucket_server_side_encryption_configuration with SSE-KMS or SSE-S3.",
                    ["AWS Well-Architected: Security Pillar"],
                )
            )
    return findings


def _first_block(value: dict | list[dict] | None) -> dict:
    if isinstance(value, list):
        return value[0] if value else {}
    return value or {}


def rule_s3_versioning(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    buckets = dict(_resources(parsed, "aws_s3_bucket"))
    enabled_versioning_resources = [
        (rname, body)
        for rname, body in _resources(parsed, "aws_s3_bucket_versioning")
        if _first_block(body.get("versioning_configuration")).get("status") == "Enabled"
    ]
    versioned = _bucket_names_referenced_by(enabled_versioning_resources)
    for name in buckets:
        if name not in versioned:
            findings.append(
                _finding(
                    review_id,
                    FindingCategory.RECOVERY,
                    f"S3 bucket '{name}' does not have versioning enabled",
                    f'resource "aws_s3_bucket" "{name}" found with no enabled versioning configuration',
                    "Accidental or malicious object deletion/overwrite cannot be recovered.",
                    'Enable aws_s3_bucket_versioning with status = "Enabled".',
                    ["AWS Well-Architected: Reliability Pillar"],
                )
            )
    return findings


def rule_security_group_open_ingress(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    for name, body in _resources(parsed, "aws_security_group"):
        for rule in (
            body.get("ingress", [])
            if isinstance(body.get("ingress"), list)
            else [body.get("ingress")]
        ):
            if not isinstance(rule, dict):
                continue
            cidrs = rule.get("cidr_blocks", [])
            if "0.0.0.0/0" not in cidrs:
                continue
            from_port = rule.get("from_port")
            to_port = rule.get("to_port")
            if from_port is None or to_port is None:
                continue
            opened_sensitive = {p for p in SENSITIVE_PORTS if from_port <= p <= to_port}
            if opened_sensitive:
                findings.append(
                    _finding(
                        review_id,
                        FindingCategory.EXPOSURE,
                        f"Security group '{name}' allows 0.0.0.0/0 ingress to sensitive port(s) {sorted(opened_sensitive)}",
                        f'resource "aws_security_group" "{name}" ingress cidr_blocks includes 0.0.0.0/0 for ports {from_port}-{to_port}',
                        "Sensitive management/database ports are reachable from the entire internet.",
                        "Restrict ingress to specific CIDR ranges or a bastion/VPN security group.",
                        ["AWS Well-Architected: Security Pillar", "CIS Controls v8: 4.4"],
                    )
                )
    return findings


def rule_ebs_encryption(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    for name, body in _resources(parsed, "aws_ebs_volume"):
        if not body.get("encrypted", False):
            findings.append(
                _finding(
                    review_id,
                    FindingCategory.ENCRYPTION,
                    f"EBS volume '{name}' is not encrypted",
                    f'resource "aws_ebs_volume" "{name}" has encrypted = false or unset',
                    "Data at rest on the volume is unencrypted.",
                    "Set encrypted = true (and kms_key_id if a CMK is required).",
                    ["AWS Well-Architected: Security Pillar"],
                )
            )
    return findings


def rule_rds_encryption(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    for name, body in _resources(parsed, "aws_db_instance"):
        if not body.get("storage_encrypted", False):
            findings.append(
                _finding(
                    review_id,
                    FindingCategory.ENCRYPTION,
                    f"RDS instance '{name}' does not have storage_encrypted set",
                    f'resource "aws_db_instance" "{name}" has storage_encrypted = false or unset',
                    "Database storage is unencrypted at rest.",
                    "Set storage_encrypted = true; note this cannot be changed after creation.",
                    ["AWS Well-Architected: Security Pillar"],
                )
            )
    return findings


def rule_rds_multi_az(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    for name, body in _resources(parsed, "aws_db_instance"):
        if not body.get("multi_az", False):
            findings.append(
                _finding(
                    review_id,
                    FindingCategory.AVAILABILITY,
                    f"RDS instance '{name}' is not configured multi_az",
                    f'resource "aws_db_instance" "{name}" has multi_az = false or unset',
                    "A single AZ failure causes database unavailability.",
                    "Set multi_az = true if the workload's availability requirement warrants it.",
                    ["AWS Well-Architected: Reliability Pillar"],
                )
            )
    return findings


def rule_iam_policy_wildcard_action_resource(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    for name, body in _resources(parsed, "aws_iam_policy"):
        policy = body.get("policy", "")
        if (
            isinstance(policy, str)
            and '"Action": "*"' in policy.replace(" ", "").replace("'", '"')
            or (isinstance(policy, str) and '"Action":"*"' in policy.replace(" ", ""))
        ):
            findings.append(
                _finding(
                    review_id,
                    FindingCategory.IAM,
                    f"IAM policy '{name}' grants wildcard Action \"*\"",
                    f'resource "aws_iam_policy" "{name}" policy document contains Action: "*"',
                    "Overly broad permissions violate least privilege and widen blast radius on compromise.",
                    "Scope the policy to the specific actions the role/function actually needs.",
                    ["AWS Well-Architected: Security Pillar", "CIS Controls v8: 5.4"],
                )
            )
    return findings


def rule_lambda_reserved_concurrency(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    for name, body in _resources(parsed, "aws_lambda_function"):
        if "reserved_concurrent_executions" not in body:
            findings.append(
                _finding(
                    review_id,
                    FindingCategory.COST,
                    f"Lambda function '{name}' has no reserved_concurrent_executions set",
                    f'resource "aws_lambda_function" "{name}" has no reserved_concurrent_executions attribute',
                    "Unbounded concurrency exposes the function (and downstream cost) to runaway invocation.",
                    "Set reserved_concurrent_executions to a deliberate cap.",
                    ["AWS Well-Architected: Cost Optimization Pillar"],
                )
            )
    return findings


def rule_cloudtrail_present(parsed: dict, review_id: str) -> list[Finding]:
    trails = dict(_resources(parsed, "aws_cloudtrail"))
    if trails:
        return []
    return [
        _finding(
            review_id,
            FindingCategory.OBSERVABILITY,
            "No aws_cloudtrail resource found in the submitted Terraform",
            "No resource of type aws_cloudtrail present in parsed configuration",
            "API activity in the account would not be recorded for audit/incident response.",
            "Add an aws_cloudtrail resource covering all regions with log file validation enabled.",
            ["AWS Well-Architected: Operational Excellence Pillar", "CIS Controls v8: 8.5"],
        )
    ]


def rule_cloudtrail_log_validation(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    for name, body in _resources(parsed, "aws_cloudtrail"):
        if not body.get("enable_log_file_validation", False):
            findings.append(
                _finding(
                    review_id,
                    FindingCategory.OBSERVABILITY,
                    f"CloudTrail '{name}' does not have log file validation enabled",
                    f'resource "aws_cloudtrail" "{name}" has enable_log_file_validation = false or unset',
                    "Log tampering after the fact would not be detectable.",
                    "Set enable_log_file_validation = true.",
                    ["CIS Controls v8: 8.5"],
                )
            )
    return findings


def rule_dynamodb_pitr(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    for name, body in _resources(parsed, "aws_dynamodb_table"):
        pitr = _first_block(body.get("point_in_time_recovery"))
        if not pitr.get("enabled"):
            findings.append(
                _finding(
                    review_id,
                    FindingCategory.RECOVERY,
                    f"DynamoDB table '{name}' does not have point-in-time recovery enabled",
                    f'resource "aws_dynamodb_table" "{name}" has no enabled point_in_time_recovery block',
                    "Accidental writes/deletes cannot be recovered to a prior point in time.",
                    "Set point_in_time_recovery { enabled = true }.",
                    ["AWS Well-Architected: Reliability Pillar"],
                )
            )
    return findings


def rule_iam_role_no_mfa_condition_on_assume(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    for name, body in _resources(parsed, "aws_iam_role"):
        policy = body.get("assume_role_policy", "")
        if (
            isinstance(policy, str)
            and '"sts:ExternalId"' not in policy
            and "saml" not in policy.lower()
            and "federated" not in policy.lower()
            and '"Service"' not in policy.replace(" ", "")
        ):
            findings.append(
                _finding(
                    review_id,
                    FindingCategory.IAM,
                    f"IAM role '{name}' assume-role policy has no external-id/federation condition",
                    f'resource "aws_iam_role" "{name}" assume_role_policy lacks an sts:ExternalId condition for non-service principals',
                    "A non-AWS-service trust relationship without a condition widens who can assume this role.",
                    "Add an sts:ExternalId condition or restrict the principal further.",
                    ["AWS Well-Architected: Security Pillar"],
                )
            )
    return findings


def rule_lambda_no_vpc_for_sensitive_env(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    for name, body in _resources(parsed, "aws_lambda_function"):
        env_vars = _first_block(body.get("environment")).get("variables", {})
        has_secret_like_env = any(
            key.lower().endswith(("_key", "_secret", "_token", "_password")) for key in env_vars
        )
        if has_secret_like_env and "vpc_config" not in body:
            findings.append(
                _finding(
                    review_id,
                    FindingCategory.EXPOSURE,
                    f"Lambda function '{name}' has secret-like environment variables and no vpc_config",
                    f'resource "aws_lambda_function" "{name}" environment variables include a key/secret/token/password-named variable with no vpc_config block',
                    "Sensitive values are more exposed to the public network path than in a VPC-scoped deployment.",
                    "Prefer Secrets Manager/SSM Parameter Store for the value, and/or run the function in a VPC.",
                    ["AWS Well-Architected: Security Pillar"],
                )
            )
    return findings


def rule_api_gateway_no_throttling(parsed: dict, review_id: str) -> list[Finding]:
    stages = dict(_resources(parsed, "aws_api_gateway_stage"))
    settings = list(_resources(parsed, "aws_api_gateway_method_settings"))
    if stages and not settings:
        return [
            _finding(
                review_id,
                FindingCategory.COST,
                "API Gateway stage(s) present with no aws_api_gateway_method_settings for throttling",
                'resource "aws_api_gateway_stage" found with no matching aws_api_gateway_method_settings resource',
                "Without throttling limits, a traffic spike or abuse pattern can drive unbounded cost/load.",
                "Add aws_api_gateway_method_settings with throttling_burst_limit/throttling_rate_limit set.",
                ["AWS Well-Architected: Cost Optimization Pillar"],
            )
        ]
    return []


def rule_public_subnet_auto_assign_ip(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    for name, body in _resources(parsed, "aws_subnet"):
        if body.get("map_public_ip_on_launch", False):
            findings.append(
                _finding(
                    review_id,
                    FindingCategory.EXPOSURE,
                    f"Subnet '{name}' auto-assigns public IPs on launch",
                    f'resource "aws_subnet" "{name}" has map_public_ip_on_launch = true',
                    "Instances launched into this subnet are publicly reachable by default.",
                    "Set map_public_ip_on_launch = false for subnets not intended to be public-facing.",
                    ["AWS Well-Architected: Security Pillar"],
                )
            )
    return findings


ALL_RULES: list[Callable[[dict, str], list[Finding]]] = [
    rule_s3_public_access_block,
    rule_s3_encryption,
    rule_s3_versioning,
    rule_security_group_open_ingress,
    rule_ebs_encryption,
    rule_rds_encryption,
    rule_rds_multi_az,
    rule_iam_policy_wildcard_action_resource,
    rule_lambda_reserved_concurrency,
    rule_cloudtrail_present,
    rule_cloudtrail_log_validation,
    rule_dynamodb_pitr,
    rule_iam_role_no_mfa_condition_on_assume,
    rule_lambda_no_vpc_for_sensitive_env,
    rule_api_gateway_no_throttling,
    rule_public_subnet_auto_assign_ip,
]


def run_rules(parsed: dict, review_id: str) -> list[Finding]:
    findings: list[Finding] = []
    for rule in ALL_RULES:
        findings.extend(rule(parsed, review_id))
    return findings


def handler(event, context):
    parsed = event["parsed"]
    review_id = event["review_id"]
    findings = run_rules(parsed, review_id)
    return {
        "status": "complete",
        "rule_version": RULE_VERSION,
        "findings": [f.model_dump(mode="json") for f in findings],
    }
