"""ArchiBrief Lambda: rule-engine.

Deterministic checks against the parsed Terraform resource tree (IAM,
exposure, encryption, availability, recovery, observability, cost — the
v1 scenario list in Work-Project-Spec.md). Every check produces zero or
more `Finding` objects of type deterministic-rule-result — never a raw
dict (Work-Project-Coding-Conventions.md "Typed-finding discipline").

Two sources feed it (ADR-0048):
- Trivy's results for the checks ArchiBrief trusts, produced by the Scan
  step and passed in as event["scanner"]. When Trivy ran, it owns those
  concerns and ArchiBrief's own rule for the same concern steps aside.
- ArchiBrief's own rules, below, for everything Trivy misses (IAM
  wildcards in any policy form, database ports open to the internet,
  public bucket policies, ...) and as the fallback when Trivy didn't run.

Resource names reach finding text only through display_name(), which
restricts them to identifier characters and truncates them (master-list
#14): rule findings are part of the reasoning model's input.

It also returns resource_summary (resource_summary.py): what the
Terraform declares and its key settings, so the model reasons from facts
instead of guessing about settings no rule mentions (#15b).
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable, Iterable

from backend.lambdas.rule_engine.hcl_eval import (
    is_created,
    policy_statements,
    resolve,
    truthy,
)
from backend.lambdas.rule_engine.resource_summary import build_resource_summary
from backend.shared.clients import S3Client
from backend.shared.models.finding import (
    ConfidenceInputs,
    Finding,
    FindingCategory,
    FindingType,
)
from backend.shared.terraform_scope import display_name, module_of, scoped_key
from backend.shared.trivy_checks import TRIVY_OWNED_CONCERNS, TRUSTED_CHECKS

RULE_VERSION = "rule_engine@2026-10-15b"

ADMIN_PORTS = {22, 3389}
SENSITIVE_PORTS = {22, 3389, 3306, 5432, 1433, 6379, 9200, 27017}
_OPEN_CIDRS = {"0.0.0.0/0", "::/0"}
_PUBLIC_ACCESS_SETTINGS = (
    "block_public_acls",
    "block_public_policy",
    "ignore_public_acls",
    "restrict_public_buckets",
)
# Set by run_rules on its working copy of `parsed` when Trivy's results
# are in use, so a rule can leave Trivy's part of a concern to Trivy.
_TRIVY_RAN = "__trivy_ran__"


def _finding(
    review_id: str,
    category: FindingCategory,
    text: str,
    evidence: str,
    risk_impact: str,
    recommendation: str,
    framework_mapping: list[str],
    rule_version: str = RULE_VERSION,
    finding_type: FindingType = FindingType.DETERMINISTIC_RULE_RESULT,
) -> Finding:
    return Finding(
        finding_id=str(uuid.uuid4()),
        review_id=review_id,
        category=category,
        type=finding_type,
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
        deterministic_rule_version=rule_version,
    )


def _resources(parsed: dict, resource_type: str) -> Iterable[tuple[str, dict]]:
    """Resources of a type that Terraform would actually create (trap f01)."""
    for key, body in parsed.get("resources", {}).get(resource_type, {}).items():
        if is_created(body, parsed):
            yield key, body


def _referenced_key(value: object, body: dict, parsed: dict, resource_type: str) -> str | None:
    """Which resource of `resource_type` an attribute points at, module-scoped.

    Follows locals and variables first (trap f03), then reads
    `<type>.<name>` out of the reference.
    """
    resolved = resolve(value, parsed, module_of(body))
    if not isinstance(resolved, str):
        return None
    match = re.search(rf"{re.escape(resource_type)}\.([A-Za-z0-9_-]+)", resolved)
    if match:
        return scoped_key(module_of(body), match.group(1))
    return None


def _bucket_keys_referenced_by(companions: Iterable[tuple[str, dict]], parsed: dict) -> set[str]:
    """Which buckets companion resources (public access block, encryption,
    versioning) attach to, by reference or by literal bucket name."""
    buckets = dict(parsed.get("resources", {}).get("aws_s3_bucket", {}))
    by_literal_name = {
        body.get("bucket"): key for key, body in buckets.items() if isinstance(body, dict)
    }
    referenced: set[str] = set()
    for _, body in companions:
        value = body.get("bucket")
        key = _referenced_key(value, body, parsed, "aws_s3_bucket")
        if key:
            referenced.add(key)
        elif isinstance(value, str) and value in by_literal_name:
            referenced.add(by_literal_name[value])
    return referenced


def _first_block(value: dict | list[dict] | None) -> dict:
    if isinstance(value, list):
        return value[0] if value else {}
    return value or {}


# --- Concern ownership ------------------------------------------------------

_RULE_CONCERNS: dict[Callable, str] = {}


def concern(name: str) -> Callable[[Callable], Callable]:
    """Tag a rule with the concern it covers, so Trivy can own it (ADR-0048)."""

    def tag(rule: Callable) -> Callable:
        _RULE_CONCERNS[rule] = name
        return rule

    return tag


# --- S3 ---------------------------------------------------------------------


@concern("s3_public_access")
def rule_s3_public_access_block(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    access_blocks = list(_resources(parsed, "aws_s3_bucket_public_access_block"))
    with_block = _bucket_keys_referenced_by(access_blocks, parsed)
    for key, body in access_blocks:
        # A block that exists but leaves settings off protects nothing (trap t10).
        disabled = [
            setting
            for setting in _PUBLIC_ACCESS_SETTINGS
            if truthy(body.get(setting, False), parsed, module_of(body)) is not True
        ]
        if not disabled:
            continue
        bucket = _referenced_key(body.get("bucket"), body, parsed, "aws_s3_bucket") or key
        name = display_name(bucket)
        findings.append(
            _finding(
                review_id,
                FindingCategory.EXPOSURE,
                f"Public access to S3 bucket '{name}' is not fully blocked",
                f'resource "aws_s3_bucket_public_access_block" "{display_name(key)}" leaves '
                f"{', '.join(disabled)} disabled",
                "A later ACL or bucket-policy change could expose the bucket's contents to the internet.",
                "Set block_public_acls, block_public_policy, ignore_public_acls and "
                "restrict_public_buckets to true.",
                ["AWS Well-Architected: Security Pillar", "SEC08-BP04"],
            )
        )
    for key, _ in _resources(parsed, "aws_s3_bucket"):
        if key not in with_block:
            name = display_name(key)
            findings.append(
                _finding(
                    review_id,
                    FindingCategory.EXPOSURE,
                    f"S3 bucket '{name}' has no aws_s3_bucket_public_access_block resource",
                    f'resource "aws_s3_bucket" "{name}" found with no matching public access block',
                    "Bucket contents may be exposed publicly if a future ACL/policy change is misconfigured.",
                    "Attach aws_s3_bucket_public_access_block with all four settings enabled.",
                    ["AWS Well-Architected: Security Pillar", "SEC08-BP04"],
                )
            )
    return findings


@concern("s3_encryption")
def rule_s3_encryption(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    encrypted = _bucket_keys_referenced_by(
        _resources(parsed, "aws_s3_bucket_server_side_encryption_configuration"), parsed
    )
    for key, _ in _resources(parsed, "aws_s3_bucket"):
        if key not in encrypted:
            name = display_name(key)
            findings.append(
                _finding(
                    review_id,
                    FindingCategory.ENCRYPTION,
                    f"S3 bucket '{name}' has no server-side encryption configuration",
                    f'resource "aws_s3_bucket" "{name}" found with no matching SSE configuration',
                    "Data at rest is unencrypted, violating baseline data-protection expectations.",
                    "Attach aws_s3_bucket_server_side_encryption_configuration with SSE-KMS or SSE-S3.",
                    ["AWS Well-Architected: Security Pillar", "SEC08-BP02"],
                )
            )
    return findings


@concern("s3_versioning")
def rule_s3_versioning(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    enabled_versioning_resources = [
        (key, body)
        for key, body in _resources(parsed, "aws_s3_bucket_versioning")
        if _first_block(body.get("versioning_configuration")).get("status") == "Enabled"
    ]
    versioned = _bucket_keys_referenced_by(enabled_versioning_resources, parsed)
    for key, _ in _resources(parsed, "aws_s3_bucket"):
        if key not in versioned:
            name = display_name(key)
            findings.append(
                _finding(
                    review_id,
                    FindingCategory.RECOVERY,
                    f"S3 bucket '{name}' does not have versioning enabled",
                    f'resource "aws_s3_bucket" "{name}" found with no enabled versioning configuration',
                    "Accidental or malicious object deletion/overwrite cannot be recovered.",
                    'Enable aws_s3_bucket_versioning with status = "Enabled".',
                    ["AWS Well-Architected: Reliability Pillar", "REL09-BP01"],
                )
            )
    return findings


def _is_public_principal(principal: object) -> bool:
    if principal == "*":
        return True
    if isinstance(principal, dict):
        aws = principal.get("AWS")
        return aws == "*" or (isinstance(aws, list) and "*" in aws)
    return False


@concern("s3_public_policy")
def rule_s3_bucket_policy_public(parsed: dict, review_id: str) -> list[Finding]:
    """A bucket policy that allows anyone, whatever the bucket is called (trap t11)."""
    findings = []
    for key, body in _resources(parsed, "aws_s3_bucket_policy"):
        statements = policy_statements(body.get("policy"), parsed, module_of(body)) or []
        public = [
            s
            for s in statements
            if s.get("Effect", "Allow") == "Allow"
            and _is_public_principal(s.get("Principal"))
            and not s.get("Condition")
        ]
        if not public:
            continue
        bucket_key = _referenced_key(body.get("bucket"), body, parsed, "aws_s3_bucket") or key
        name = display_name(bucket_key)
        actions = sorted({str(a) for s in public for a in _as_list(s.get("Action"))})
        findings.append(
            _finding(
                review_id,
                FindingCategory.EXPOSURE,
                f"S3 bucket '{name}' has a bucket policy that allows anyone (Principal \"*\")",
                f'resource "aws_s3_bucket_policy" "{display_name(key)}" allows Principal "*" '
                f"with no condition for {', '.join(actions)[:120]}",
                "Anyone on the internet can perform these actions on the bucket's objects.",
                "Remove the public statement, or restrict it with a condition (for example a "
                "CloudFront origin access control or a specific account).",
                ["AWS Well-Architected: Security Pillar", "SEC08-BP04"],
            )
        )
    return findings


# --- Network ----------------------------------------------------------------


def _as_list(value: object) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _port_range(from_port: object, to_port: object, protocol: object) -> range | None:
    if str(protocol) in ("-1", "all"):
        return range(65536)
    try:
        start, end = int(from_port), int(to_port)
    except (TypeError, ValueError):
        return None
    if start == 0 and end == 0 and str(protocol) in ("-1", "all"):
        return range(65536)
    return range(start, end + 1)


def _exposed_ports(ports: range, trivy_ran: bool) -> set[int]:
    """Sensitive ports in range; SSH/RDP are Trivy's (AWS-0107) when it ran.

    All-traffic rules used to be left to Trivy entirely, but its finding
    only names SSH/RDP, so a database open on every port (FEC demo) read
    as an admin-port issue. The database ports are reported here.
    """
    sensitive = SENSITIVE_PORTS - ADMIN_PORTS if trivy_ran else SENSITIVE_PORTS
    return {p for p in sensitive if p in ports}


def _open_ingress_rules(parsed: dict) -> Iterable[tuple[str, str, set[str], range]]:
    """Every internet-open ingress rule, whichever resource type declares it.

    Yields (resource_type, key, open cidrs, ports). Covers inline ingress
    blocks, aws_security_group_rule and aws_vpc_security_group_ingress_rule
    (traps t07, t08), and IPv6 (trap t09).
    """
    for key, body in _resources(parsed, "aws_security_group"):
        module = module_of(body)
        for rule in _as_list(body.get("ingress")):
            if not isinstance(rule, dict):
                continue
            cidrs = {
                str(c)
                for c in _as_list(resolve(rule.get("cidr_blocks"), parsed, module))
                + _as_list(resolve(rule.get("ipv6_cidr_blocks"), parsed, module))
            } & _OPEN_CIDRS
            ports = _port_range(rule.get("from_port"), rule.get("to_port"), rule.get("protocol"))
            if cidrs and ports:
                yield "aws_security_group", key, cidrs, ports

    for key, body in _resources(parsed, "aws_security_group_rule"):
        if body.get("type") != "ingress":
            continue
        module = module_of(body)
        cidrs = {
            str(c)
            for c in _as_list(resolve(body.get("cidr_blocks"), parsed, module))
            + _as_list(resolve(body.get("ipv6_cidr_blocks"), parsed, module))
        } & _OPEN_CIDRS
        ports = _port_range(body.get("from_port"), body.get("to_port"), body.get("protocol"))
        if cidrs and ports:
            yield "aws_security_group_rule", key, cidrs, ports

    for key, body in _resources(parsed, "aws_vpc_security_group_ingress_rule"):
        module = module_of(body)
        cidrs = {
            str(resolve(body.get("cidr_ipv4"), parsed, module)),
            str(resolve(body.get("cidr_ipv6"), parsed, module)),
        } & _OPEN_CIDRS
        ports = _port_range(body.get("from_port"), body.get("to_port"), body.get("ip_protocol"))
        if cidrs and ports:
            yield "aws_vpc_security_group_ingress_rule", key, cidrs, ports


@concern("sg_open_ingress")
def rule_security_group_open_ingress(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    trivy_ran = bool(parsed.get(_TRIVY_RAN))
    for resource_type, key, cidrs, ports in _open_ingress_rules(parsed):
        exposed = _exposed_ports(ports, trivy_ran)
        if not exposed:
            continue
        name = display_name(key)
        cidr_text = " and ".join(sorted(cidrs))
        span = "all ports" if len(ports) == 65536 else f"ports {ports.start}-{ports.stop - 1}"
        findings.append(
            _finding(
                review_id,
                FindingCategory.EXPOSURE,
                f"Security group rule '{name}' allows {cidr_text} ingress to sensitive port(s) "
                f"{sorted(exposed)}",
                f'resource "{resource_type}" "{name}" allows {cidr_text} for {span}',
                "Sensitive management/database ports are reachable from the entire internet.",
                "Restrict ingress to specific CIDR ranges or a bastion/VPN security group.",
                ["AWS Well-Architected: Security Pillar", "SEC05-BP02", "CIS Controls v8: 4.4"],
            )
        )
    return findings


@concern("subnet_public_ip")
def rule_public_subnet_auto_assign_ip(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    for key, body in _resources(parsed, "aws_subnet"):
        if truthy(body.get("map_public_ip_on_launch", False), parsed, module_of(body)):
            name = display_name(key)
            findings.append(
                _finding(
                    review_id,
                    FindingCategory.EXPOSURE,
                    f"Subnet '{name}' auto-assigns public IPs on launch",
                    f'resource "aws_subnet" "{name}" has map_public_ip_on_launch = true',
                    "Instances launched into this subnet are publicly reachable by default.",
                    "Set map_public_ip_on_launch = false for subnets not intended to be public-facing.",
                    ["AWS Well-Architected: Security Pillar", "SEC05-BP01"],
                )
            )
    return findings


# --- Encryption, availability, recovery ------------------------------------


@concern("ebs_encryption")
def rule_ebs_encryption(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    for key, body in _resources(parsed, "aws_ebs_volume"):
        if not truthy(body.get("encrypted", False), parsed, module_of(body)):
            name = display_name(key)
            findings.append(
                _finding(
                    review_id,
                    FindingCategory.ENCRYPTION,
                    f"EBS volume '{name}' is not encrypted",
                    f'resource "aws_ebs_volume" "{name}" has encrypted = false or unset',
                    "Data at rest on the volume is unencrypted.",
                    "Set encrypted = true (and kms_key_id if a CMK is required).",
                    ["AWS Well-Architected: Security Pillar", "SEC08-BP02"],
                )
            )
    return findings


@concern("rds_encryption")
def rule_rds_encryption(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    for key, body in _resources(parsed, "aws_db_instance"):
        # Resolved through variable defaults (trap t13).
        if not truthy(body.get("storage_encrypted", False), parsed, module_of(body)):
            name = display_name(key)
            findings.append(
                _finding(
                    review_id,
                    FindingCategory.ENCRYPTION,
                    f"RDS instance '{name}' does not have storage_encrypted set",
                    f'resource "aws_db_instance" "{name}" has storage_encrypted = false or unset',
                    "Database storage is unencrypted at rest.",
                    "Set storage_encrypted = true; note this cannot be changed after creation.",
                    ["AWS Well-Architected: Security Pillar", "SEC08-BP02"],
                )
            )
    return findings


@concern("rds_public")
def rule_rds_publicly_accessible(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    # Aurora's per-instance resource carries the same setting (FEC demo).
    instances = [
        (resource_type, key, body)
        for resource_type in ("aws_db_instance", "aws_rds_cluster_instance")
        for key, body in _resources(parsed, resource_type)
    ]
    for resource_type, key, body in instances:
        if truthy(body.get("publicly_accessible", False), parsed, module_of(body)):
            name = display_name(key)
            findings.append(
                _finding(
                    review_id,
                    FindingCategory.EXPOSURE,
                    f"RDS instance '{name}' is publicly accessible",
                    f'resource "{resource_type}" "{name}" has publicly_accessible = true',
                    "The database gets a public endpoint and is one security-group mistake "
                    "from the internet.",
                    "Set publicly_accessible = false and reach the database from inside the VPC.",
                    ["AWS Well-Architected: Security Pillar", "SEC05-BP01"],
                )
            )
    return findings


@concern("rds_multi_az")
def rule_rds_multi_az(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    for key, body in _resources(parsed, "aws_db_instance"):
        if not truthy(body.get("multi_az", False), parsed, module_of(body)):
            name = display_name(key)
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


@concern("dynamodb_pitr")
def rule_dynamodb_pitr(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    for key, body in _resources(parsed, "aws_dynamodb_table"):
        pitr = _first_block(body.get("point_in_time_recovery"))
        if not truthy(pitr.get("enabled", False), parsed, module_of(body)):
            name = display_name(key)
            findings.append(
                _finding(
                    review_id,
                    FindingCategory.RECOVERY,
                    f"DynamoDB table '{name}' does not have point-in-time recovery enabled",
                    f'resource "aws_dynamodb_table" "{name}" has no enabled point_in_time_recovery block',
                    "Accidental writes/deletes cannot be recovered to a prior point in time.",
                    "Set point_in_time_recovery { enabled = true }.",
                    ["AWS Well-Architected: Reliability Pillar", "REL09-BP01"],
                )
            )
    return findings


# --- IAM --------------------------------------------------------------------

# Every place a Terraform config can carry an IAM permissions policy.
_POLICY_ATTRIBUTES = (
    ("aws_iam_policy", "policy"),
    ("aws_iam_role_policy", "policy"),
    ("aws_iam_user_policy", "policy"),
    ("aws_iam_group_policy", "policy"),
)


def _permission_policies(parsed: dict) -> Iterable[tuple[str, str, list[dict]]]:
    for resource_type, attribute in _POLICY_ATTRIBUTES:
        for key, body in _resources(parsed, resource_type):
            statements = policy_statements(body.get(attribute), parsed, module_of(body))
            if statements:
                yield resource_type, key, statements
    for key, body in _resources(parsed, "aws_iam_role"):
        for inline in _as_list(body.get("inline_policy")):
            if isinstance(inline, dict):
                statements = policy_statements(inline.get("policy"), parsed, module_of(body))
                if statements:
                    yield "aws_iam_role", key, statements


def _wildcard_grants(statements: list[dict]) -> list[str]:
    """Actions an Allow statement grants as a wildcard on every resource."""
    grants: list[str] = []
    for statement in statements:
        if statement.get("Effect", "Allow") != "Allow":
            continue
        if "*" not in {str(r) for r in _as_list(statement.get("Resource"))}:
            continue
        for action in _as_list(statement.get("Action")):
            action = str(action)
            if action == "*" or action.endswith(":*"):
                grants.append(action)
    return sorted(set(grants))


@concern("iam_wildcard")
def rule_iam_policy_wildcard_action_resource(parsed: dict, review_id: str) -> list[Finding]:
    """Wildcard grants in any policy form: heredoc, jsonencode(), policy
    documents, variable defaults, inline role policies (traps t01-t05)."""
    findings = []
    for resource_type, key, statements in _permission_policies(parsed):
        grants = _wildcard_grants(statements)
        if not grants:
            continue
        name = display_name(key)
        if "*" in grants:
            text = f"IAM policy '{name}' grants wildcard Action \"*\" on all resources (full admin)"
        else:
            text = f"IAM policy '{name}' grants wildcard {', '.join(grants)} on all resources"
        findings.append(
            _finding(
                review_id,
                FindingCategory.IAM,
                text,
                f'resource "{resource_type}" "{name}" allows {", ".join(grants)} on Resource "*"',
                "Overly broad permissions violate least privilege and widen blast radius on compromise.",
                "Scope the policy to the specific actions and resource ARNs the role actually needs.",
                ["AWS Well-Architected: Security Pillar", "SEC03-BP02", "CIS Controls v8: 5.4"],
            )
        )
    return findings


_TRUST_CONDITIONS = ("sts:externalid", "aws:multifactorauthpresent", "aws:principalorgid")


@concern("iam_trust")
def rule_iam_role_no_mfa_condition_on_assume(parsed: dict, review_id: str) -> list[Finding]:
    """AWS-account principals trusted with no condition. Service and
    federated trusts are fine (trap f02); an unresolvable policy is not
    flagged, since the rule can't see what it says."""
    findings = []
    for key, body in _resources(parsed, "aws_iam_role"):
        statements = policy_statements(body.get("assume_role_policy"), parsed, module_of(body))
        if not statements:
            continue
        for statement in statements:
            principal = statement.get("Principal")
            if statement.get("Effect", "Allow") != "Allow" or not isinstance(principal, dict):
                continue
            if "AWS" not in principal:
                continue
            condition_keys = json.dumps(statement.get("Condition", {})).lower()
            if any(k in condition_keys for k in _TRUST_CONDITIONS):
                continue
            name = display_name(key)
            findings.append(
                _finding(
                    review_id,
                    FindingCategory.IAM,
                    f"IAM role '{name}' assume-role policy has no external-id/federation condition",
                    f'resource "aws_iam_role" "{name}" trusts an AWS principal with no '
                    "sts:ExternalId, MFA or organization condition",
                    "Anyone in the trusted account who can call sts:AssumeRole can use this role.",
                    "Add an sts:ExternalId, aws:MultiFactorAuthPresent or aws:PrincipalOrgID condition.",
                    ["AWS Well-Architected: Security Pillar", "SEC03-BP02"],
                )
            )
            break
    return findings


# --- Credentials reachable by running code ----------------------------------
# Together these two are the attack path publicly reported for the 2019
# Capital One breach: a request forgery on a server reads its role's
# credentials from the instance metadata service (IMDSv1 answers plain
# GETs), and a role with broad permissions turns that into reading every
# bucket. Trivy (AWS-0028) only covers the first half, and not on every
# run (it can be unavailable), so ArchiBrief owns both.

# Principals whose role credentials live inside running code.
_COMPUTE_SERVICES = {
    "ec2.amazonaws.com",
    "lambda.amazonaws.com",
    "ecs-tasks.amazonaws.com",
    "pods.eks.amazonaws.com",
}
# AWS-managed policies broad enough that leaked credentials mean
# account-wide damage. Named ones appear in finding text as-is; any other
# "...FullAccess" policy is described generically, so a made-up policy
# name from the submission never reaches the model.
_BROAD_MANAGED_POLICIES = frozenset(
    {
        "AdministratorAccess",
        "PowerUserAccess",
        "IAMFullAccess",
        "AmazonS3FullAccess",
        "AmazonDynamoDBFullAccess",
        "AmazonEC2FullAccess",
        "AmazonRDSFullAccess",
        "AmazonSQSFullAccess",
        "AmazonSNSFullAccess",
        "AmazonSSMFullAccess",
        "AWSLambda_FullAccess",
        "SecretsManagerReadWrite",
    }
)
_MANAGED_POLICY_ARN = re.compile(
    r":iam::aws:policy/(?:[A-Za-z0-9_+=,.@-]+/)*([A-Za-z0-9_+=,.@-]+)$"
)


def _broad_policy_label(arn: object, parsed: dict, module: str) -> str | None:
    resolved = resolve(arn, parsed, module)
    if not isinstance(resolved, str):
        return None
    match = _MANAGED_POLICY_ARN.search(resolved)
    if not match:
        return None
    name = match.group(1)
    if name in _BROAD_MANAGED_POLICIES:
        return name
    if name.endswith("FullAccess"):
        return "an AWS-managed *FullAccess policy"
    return None


def _trusts_compute(body: dict, parsed: dict) -> bool:
    statements = policy_statements(body.get("assume_role_policy"), parsed, module_of(body)) or []
    for statement in statements:
        principal = statement.get("Principal")
        if statement.get("Effect", "Allow") != "Allow" or not isinstance(principal, dict):
            continue
        if {str(s) for s in _as_list(principal.get("Service"))} & _COMPUTE_SERVICES:
            return True
    return False


def _role_key(value: object, body: dict, parsed: dict) -> str | None:
    """A role referenced by an attachment, by reference or by literal name."""
    key = _referenced_key(value, body, parsed, "aws_iam_role")
    if key:
        return key
    for role_key, role in parsed.get("resources", {}).get("aws_iam_role", {}).items():
        if isinstance(role, dict) and isinstance(value, str) and role.get("name") == value:
            return role_key
    return None


def _broad_compute_roles(parsed: dict) -> dict[str, list[str]]:
    """{role key: [broad policy labels]} for roles that running code assumes."""
    attached: dict[str, list[str]] = {}

    def add(role_key: str | None, arn: object, module: str) -> None:
        label = _broad_policy_label(arn, parsed, module)
        if role_key and label:
            attached.setdefault(role_key, []).append(label)

    for key, body in _resources(parsed, "aws_iam_role"):
        for arn in _as_list(resolve(body.get("managed_policy_arns"), parsed, module_of(body))):
            add(key, arn, module_of(body))
    for _, body in _resources(parsed, "aws_iam_role_policy_attachment"):
        add(_role_key(body.get("role"), body, parsed), body.get("policy_arn"), module_of(body))
    for _, body in _resources(parsed, "aws_iam_policy_attachment"):
        roles = resolve(body.get("roles"), parsed, module_of(body))
        for role in _as_list(roles):
            add(_role_key(role, body, parsed), body.get("policy_arn"), module_of(body))

    roles = dict(_resources(parsed, "aws_iam_role"))
    return {
        key: sorted(set(labels))
        for key, labels in attached.items()
        if key in roles and _trusts_compute(roles[key], parsed)
    }


@concern("iam_compute_broad_managed")
def rule_compute_role_broad_managed_policy(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    for key, labels in sorted(_broad_compute_roles(parsed).items()):
        name = display_name(key)
        policies = ", ".join(labels)
        findings.append(
            _finding(
                review_id,
                FindingCategory.IAM,
                f"IAM role '{name}' is used by running code and has {policies}",
                f'resource "aws_iam_role" "{name}" trusts a compute service '
                f"(EC2, Lambda, ECS tasks or EKS pods) and has {policies} attached",
                "Anyone who gets code running on this compute, or tricks it into a "
                "request forgery, gets these permissions across the whole account.",
                "Replace the managed policy with a customer-managed one that names only "
                "the actions and resource ARNs this workload uses.",
                ["AWS Well-Architected: Security Pillar", "SEC03-BP02", "CIS Controls v8: 5.4"],
            )
        )
    return findings


def _profile_role(profile_ref: object, body: dict, parsed: dict) -> str | None:
    profile_key = _referenced_key(profile_ref, body, parsed, "aws_iam_instance_profile")
    profiles = parsed.get("resources", {}).get("aws_iam_instance_profile", {})
    profile = profiles.get(profile_key) if profile_key else None
    if not isinstance(profile, dict):
        return None
    return _role_key(profile.get("role"), profile, parsed)


def _account_requires_imdsv2(parsed: dict) -> bool:
    return any(
        resolve(body.get("http_tokens"), parsed, module_of(body)) == "required"
        for _, body in _resources(parsed, "aws_ec2_instance_metadata_defaults")
    )


@concern("ec2_imdsv2")
def rule_ec2_imdsv2_required(parsed: dict, review_id: str) -> list[Finding]:
    """Instances and launch templates that don't require IMDSv2 tokens.

    Unset is flagged: whether IMDSv1 then works depends on the AMI and the
    account default, which the code doesn't show, unless the code sets
    that account default itself (aws_ec2_instance_metadata_defaults).
    """
    if _account_requires_imdsv2(parsed):
        return []
    broad_roles = _broad_compute_roles(parsed)
    findings = []
    for resource_type in ("aws_instance", "aws_launch_template"):
        for key, body in _resources(parsed, resource_type):
            options = _first_block(body.get("metadata_options"))
            module = module_of(body)
            tokens = resolve(options.get("http_tokens"), parsed, module)
            if tokens == "required":
                continue
            if resolve(options.get("http_endpoint"), parsed, module) == "disabled":
                continue
            name = display_name(key)
            setting = "is not set" if tokens is None else 'is not "required"'
            risk = (
                "IMDSv1 answers plain HTTP GETs, so a request forgery or open proxy on this "
                "server can read its role's temporary credentials."
            )
            if resource_type == "aws_launch_template":
                profile = _first_block(body.get("iam_instance_profile"))
                role_key = _profile_role(profile.get("name") or profile.get("arn"), body, parsed)
            else:
                role_key = _profile_role(body.get("iam_instance_profile"), body, parsed)
            if role_key in broad_roles:
                risk += (
                    f" Its role '{display_name(role_key)}' has "
                    f"{', '.join(broad_roles[role_key])}, so those credentials reach far "
                    "beyond this server."
                )
            kind = "EC2 instance" if resource_type == "aws_instance" else "Launch template"
            findings.append(
                _finding(
                    review_id,
                    FindingCategory.EXPOSURE,
                    f"{kind} '{name}' does not require IMDSv2 tokens",
                    f'resource "{resource_type}" "{name}" metadata_options.http_tokens {setting}',
                    risk,
                    'Set metadata_options { http_tokens = "required" } (or require IMDSv2 '
                    "account-wide with aws_ec2_instance_metadata_defaults).",
                    ["AWS Well-Architected: Security Pillar", "SEC06-BP05"],
                )
            )
    return findings


# --- Observability and cost -------------------------------------------------


@concern("lambda_concurrency")
def rule_lambda_reserved_concurrency(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    for key, body in _resources(parsed, "aws_lambda_function"):
        if "reserved_concurrent_executions" not in body:
            name = display_name(key)
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


@concern("cloudtrail_present")
def rule_cloudtrail_present(parsed: dict, review_id: str) -> list[Finding]:
    if any(True for _ in _resources(parsed, "aws_cloudtrail")):
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


@concern("cloudtrail_log_validation")
def rule_cloudtrail_log_validation(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    for key, body in _resources(parsed, "aws_cloudtrail"):
        if not truthy(body.get("enable_log_file_validation", False), parsed, module_of(body)):
            name = display_name(key)
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


@concern("lambda_secret_env")
def rule_lambda_no_vpc_for_sensitive_env(parsed: dict, review_id: str) -> list[Finding]:
    findings = []
    for key, body in _resources(parsed, "aws_lambda_function"):
        env_vars = _first_block(body.get("environment")).get("variables", {})
        if not isinstance(env_vars, dict):
            continue
        has_secret_like_env = any(
            k.lower().endswith(("_key", "_secret", "_token", "_password")) for k in env_vars
        )
        if has_secret_like_env and "vpc_config" not in body:
            name = display_name(key)
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


@concern("apigw_throttling")
def rule_api_gateway_no_throttling(parsed: dict, review_id: str) -> list[Finding]:
    stages = list(_resources(parsed, "aws_api_gateway_stage"))
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


ALL_RULES: list[Callable[[dict, str], list[Finding]]] = [
    rule_s3_public_access_block,
    rule_s3_encryption,
    rule_s3_versioning,
    rule_s3_bucket_policy_public,
    rule_security_group_open_ingress,
    rule_ebs_encryption,
    rule_rds_encryption,
    rule_rds_publicly_accessible,
    rule_rds_multi_az,
    rule_iam_policy_wildcard_action_resource,
    rule_lambda_reserved_concurrency,
    rule_cloudtrail_present,
    rule_cloudtrail_log_validation,
    rule_dynamodb_pitr,
    rule_iam_role_no_mfa_condition_on_assume,
    rule_compute_role_broad_managed_policy,
    rule_ec2_imdsv2_required,
    rule_lambda_no_vpc_for_sensitive_env,
    rule_api_gateway_no_throttling,
    rule_public_subnet_auto_assign_ip,
]


# --- Trivy results ----------------------------------------------------------

_SAFE_PATH = re.compile(r"[^A-Za-z0-9_./-]")


def _safe_file(path: object) -> str:
    return _SAFE_PATH.sub("", str(path))[:120]


def _subject_key(result: dict, parsed: dict) -> str:
    """The resource a Trivy result is really about. A public access block
    result is reported against its bucket (trap t10)."""
    key = result["resource_key"]
    if result["resource_type"] != "aws_s3_bucket_public_access_block":
        return key
    body = parsed.get("resources", {}).get("aws_s3_bucket_public_access_block", {}).get(key)
    if isinstance(body, dict):
        return _referenced_key(body.get("bucket"), body, parsed, "aws_s3_bucket") or key
    return key


def scanner_findings(scanner: dict, parsed: dict, review_id: str) -> list[Finding]:
    """One finding per (concern, resource) from Trivy's trusted results."""
    version = f"{RULE_VERSION}+trivy@{scanner.get('version', 'unknown')}"
    grouped: dict[tuple[str, str], list[dict]] = {}
    for result in scanner.get("results", []):
        check = TRUSTED_CHECKS.get(result.get("check_id", ""))
        if check is None:
            continue
        grouped.setdefault((check.concern, _subject_key(result, parsed)), []).append(result)

    findings = []
    for (_, key), results in grouped.items():
        checks = [TRUSTED_CHECKS[r["check_id"]] for r in results]
        first = results[0]
        name = display_name(key)
        ids = sorted({r["check_id"] for r in results})
        lines = sorted({r["start_line"] for r in results if r.get("start_line")})
        location = _safe_file(first.get("file", ""))
        if lines:
            location += f" line {lines[0]}" if len(lines) == 1 else f" lines {lines[0]}-{lines[-1]}"
        details = "; ".join(dict.fromkeys(c.detail for c in checks))
        findings.append(
            _finding(
                review_id,
                FindingCategory(checks[0].category),
                checks[0].title.format(name=name),
                f'resource "{first["resource_type"]}" "{display_name(first["resource_key"])}" '
                f"at {location}: {details} (Trivy {', '.join(ids)})",
                checks[0].risk,
                checks[0].recommendation,
                [*checks[0].framework, *(f"Trivy {i}" for i in ids)],
                rule_version=version,
            )
        )
    return findings


def _scanner_unavailable(review_id: str) -> Finding:
    return _finding(
        review_id,
        FindingCategory.OBSERVABILITY,
        "The Trivy scanner didn't run for this review; only ArchiBrief's own rules were applied",
        "The scan step reported the scanner as unavailable",
        "Issues that only Trivy detects may be missing from this report.",
        "Re-run the review later for a full scan.",
        [],
        finding_type=FindingType.NOT_OBSERVABLE,
    )


def run_rules(parsed: dict, review_id: str, scanner: dict | None = None) -> list[Finding]:
    """ArchiBrief's rules, plus Trivy's trusted results when the Scan step ran.

    scanner=None means no scan step was involved (unit tests, local runs);
    every ArchiBrief rule runs. A scanner that reported "unavailable" also
    falls back to every rule, and the report says so.
    """
    trivy_ran = bool(scanner) and scanner.get("status") == "ok"
    working = {**parsed, _TRIVY_RAN: trivy_ran}
    findings: list[Finding] = []
    for rule in ALL_RULES:
        if trivy_ran and _RULE_CONCERNS.get(rule) in TRIVY_OWNED_CONCERNS:
            continue
        findings.extend(rule(working, review_id))
    if trivy_ran:
        findings.extend(scanner_findings(scanner, working, review_id))
    elif scanner is not None:
        findings.append(_scanner_unavailable(review_id))
    return findings


def load_parsed(event: dict) -> dict:
    """Parsed Terraform comes inline (tests/local) or, in the deployed
    workflow, as an S3 reference written by Ingest (Codex F07)."""
    if "parsed_s3_key" in event:
        body = S3Client(bucket=event["report_bucket"]).get_object(event["parsed_s3_key"])
        return json.loads(body)
    return event["parsed"]


def handler(event, context):
    parsed = load_parsed(event)
    review_id = event["review_id"]
    findings = run_rules(parsed, review_id, scanner=event.get("scanner"))
    return {
        "status": "complete",
        "rule_version": RULE_VERSION,
        "findings": [f.model_dump(mode="json") for f in findings],
        "resource_summary": build_resource_summary(parsed),
    }
