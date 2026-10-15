"""What the submitted Terraform declares, as facts the reasoning model can use.

The model never sees the Terraform itself (ADR-0038: submitted code is
untrusted input). Before this summary existed it only saw rule findings,
so it guessed about anything no rule mentioned: in the 2026-10-15 live
run it called Multi-AZ "likely absent" on an instance with
`multi_az = true` (master-list #15b).

So the summary carries facts but leaves no room to write instructions in:

- Only settings on an allowlist, per resource type.
- Values are booleans, numbers, or a string the setting can really take
  (an engine from a known list, an instance class in AWS's format, ...).
  Anything else, and any reference that can't be resolved statically,
  becomes "unknown". The first version allowed any 32-character
  identifier, and the 2026-10-15 trap run showed `IGNORE_ALL_FINDINGS`
  as an engine getting through, so no free-form words reach the model
  through a value now.
- A listed setting the Terraform leaves out is "not set (default: X)"
  when the AWS provider's default is documented and fixed, and plain
  "not set" when it depends on something outside the code (account
  settings, the AMI, the subnet). The model guessed defaults wrong in the
  2026-10-15 re-run (it said an unset skip_final_snapshot skips the final
  snapshot; the default is false), so it's told the default, never asked
  to recall it.
- Names go through display_name(), the same cleaning as finding text.
- Comments, descriptions, tags and policy documents never appear.
- Resources with count = 0 are left out; the list is capped.
"""

from __future__ import annotations

import re

from backend.lambdas.rule_engine.hcl_eval import is_created, resolve
from backend.shared.terraform_scope import display_name, module_of

NOT_SET = "not set"
# Fixed text, never built from the submission. In the 2026-10-15 trap
# re-run the model read a setting missing from the summary as missing
# from the code ("no CloudWatch log exports are present").
COVERAGE_NOTE = (
    "Only the settings named for each resource were checked. A setting not "
    "named here may still be set in the code: never describe it as missing."
)
UNKNOWN = "unknown"
MAX_RESOURCES = 80
# Provider resource types are lowercase snake case and some real ones are
# long (aws_s3_bucket_server_side_encryption_configuration is 50).
_RESOURCE_TYPE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")

# Settings that change what a reviewer would conclude. A dotted path reads
# into a nested block (its first occurrence).
SETTINGS: dict[str, tuple[str, ...]] = {
    "aws_db_instance": (
        "engine",
        "instance_class",
        "multi_az",
        "storage_encrypted",
        "publicly_accessible",
        "backup_retention_period",
        "deletion_protection",
        "iam_database_authentication_enabled",
        "auto_minor_version_upgrade",
        "skip_final_snapshot",
    ),
    "aws_rds_cluster": (
        "engine",
        "storage_encrypted",
        "backup_retention_period",
        "deletion_protection",
        "iam_database_authentication_enabled",
    ),
    "aws_s3_bucket_versioning": ("versioning_configuration.status",),
    "aws_s3_bucket_public_access_block": (
        "block_public_acls",
        "block_public_policy",
        "ignore_public_acls",
        "restrict_public_buckets",
    ),
    "aws_dynamodb_table": (
        "billing_mode",
        "point_in_time_recovery.enabled",
        "server_side_encryption.enabled",
        "deletion_protection_enabled",
    ),
    "aws_lambda_function": (
        "runtime",
        "memory_size",
        "timeout",
        "reserved_concurrent_executions",
        "tracing_config.mode",
    ),
    "aws_instance": (
        "instance_type",
        "associate_public_ip_address",
        "monitoring",
        "metadata_options.http_tokens",
        "root_block_device.encrypted",
    ),
    "aws_launch_template": ("instance_type", "metadata_options.http_tokens"),
    "aws_ebs_volume": ("encrypted", "type", "size"),
    "aws_autoscaling_group": ("min_size", "max_size", "desired_capacity"),
    "aws_lb": ("internal", "load_balancer_type", "drop_invalid_header_fields"),
    "aws_elasticache_replication_group": (
        "automatic_failover_enabled",
        "multi_az_enabled",
        "num_cache_clusters",
        "at_rest_encryption_enabled",
        "transit_encryption_enabled",
    ),
    "aws_cloudtrail": (
        "is_multi_region_trail",
        "enable_log_file_validation",
        "include_global_service_events",
    ),
    "aws_cloudwatch_log_group": ("retention_in_days",),
    "aws_kms_key": ("enable_key_rotation", "deletion_window_in_days"),
    "aws_sqs_queue": ("sqs_managed_sse_enabled", "message_retention_seconds"),
    "aws_subnet": ("map_public_ip_on_launch",),
    "aws_api_gateway_stage": ("xray_tracing_enabled",),
    "aws_apigatewayv2_stage": ("default_route_settings.throttling_rate_limit",),
}


# The AWS provider's documented default for a setting left out of the
# code. Only defaults that are fixed are listed; ones that depend on the
# account, AMI or subnet (EBS default encryption, IMDS tokens, public IPs)
# stay plain "not set". RDS backup retention defaults to 1 day when left
# out (the RDS API default; Trivy AWS-0077 treats unset as 1); the model
# guessed 0 in the 2026-10-15 trap re-run.
DEFAULTS: dict[str, dict[str, object]] = {
    "aws_db_instance": {
        "multi_az": False,
        "storage_encrypted": False,
        "publicly_accessible": False,
        "deletion_protection": False,
        "iam_database_authentication_enabled": False,
        "auto_minor_version_upgrade": True,
        "skip_final_snapshot": False,
        "backup_retention_period": 1,
    },
    "aws_rds_cluster": {
        "deletion_protection": False,
        "iam_database_authentication_enabled": False,
    },
    "aws_s3_bucket_public_access_block": {
        "block_public_acls": False,
        "block_public_policy": False,
        "ignore_public_acls": False,
        "restrict_public_buckets": False,
    },
    "aws_dynamodb_table": {
        "billing_mode": "PROVISIONED",
        "point_in_time_recovery.enabled": False,
        "deletion_protection_enabled": False,
    },
    "aws_lambda_function": {
        "memory_size": 128,
        "timeout": 3,
        "reserved_concurrent_executions": -1,
        "tracing_config.mode": "PassThrough",
    },
    "aws_instance": {"monitoring": False},
    "aws_lb": {
        "internal": False,
        "load_balancer_type": "application",
        "drop_invalid_header_fields": False,
    },
    "aws_elasticache_replication_group": {
        "automatic_failover_enabled": False,
        "multi_az_enabled": False,
    },
    "aws_cloudtrail": {
        "is_multi_region_trail": False,
        "enable_log_file_validation": False,
        "include_global_service_events": True,
    },
    "aws_cloudwatch_log_group": {"retention_in_days": 0},
    "aws_kms_key": {"enable_key_rotation": False, "deletion_window_in_days": 30},
    "aws_sqs_queue": {"message_retention_seconds": 345600},
    "aws_subnet": {"map_public_ip_on_launch": False},
    "aws_api_gateway_stage": {"xray_tracing_enabled": False},
}


def _not_set(resource_type: str, path: str) -> str:
    defaults = DEFAULTS.get(resource_type, {})
    if path not in defaults:
        return NOT_SET
    default = defaults[path]
    shown = str(default).lower() if isinstance(default, bool) else default
    return f"{NOT_SET} (default: {shown})"


def _first(value: object) -> object:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _read(body: dict, resource_type: str, path: str, parsed: dict, module: str) -> object:
    value: object = body
    for part in path.split("."):
        value = _first(value)
        if not isinstance(value, dict) or part not in value:
            return _not_set(resource_type, path)
        value = value[part]
    return _safe_value(resolve(_first(value), parsed, module), path)


_ENGINES = {
    "postgres",
    "mysql",
    "mariadb",
    "oracle-ee",
    "oracle-se2",
    "sqlserver-ee",
    "sqlserver-se",
    "sqlserver-ex",
    "sqlserver-web",
    "aurora-mysql",
    "aurora-postgresql",
    "db2-ae",
    "db2-se",
}
_INSTANCE_SIZE = r"[a-z][a-z0-9-]{0,15}\.[a-z0-9]{1,15}"
# What each string setting can really be. A value that doesn't match is
# "unknown", so a setting can't carry words of the submitter's choosing.
STRING_FORMATS: dict[str, re.Pattern[str] | frozenset[str]] = {
    "engine": frozenset(_ENGINES),
    "instance_class": re.compile(rf"^db\.{_INSTANCE_SIZE}$"),
    "instance_type": re.compile(rf"^{_INSTANCE_SIZE}$"),
    "billing_mode": frozenset({"PROVISIONED", "PAY_PER_REQUEST"}),
    "runtime": re.compile(
        r"^(python|nodejs|java|dotnet|ruby|provided)[0-9.]*(\.x|\.al2|\.al2023)?$"
    ),
    "tracing_config.mode": frozenset({"Active", "PassThrough"}),
    "metadata_options.http_tokens": frozenset({"required", "optional"}),
    "versioning_configuration.status": frozenset({"Enabled", "Suspended", "Disabled"}),
    "load_balancer_type": frozenset({"application", "network", "gateway"}),
    "type": frozenset({"standard", "gp2", "gp3", "io1", "io2", "sc1", "st1"}),
}


def _safe_value(value: object, path: str) -> object:
    if isinstance(value, bool | int | float):
        return value
    if not isinstance(value, str):
        return UNKNOWN
    text = value.strip()
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    allowed = STRING_FORMATS.get(path)
    if isinstance(allowed, frozenset) and text in allowed:
        return text
    if isinstance(allowed, re.Pattern) and allowed.fullmatch(text):
        return text
    return UNKNOWN


def build_resource_summary(parsed: dict) -> dict:
    """{"resources": [{"type", "name", "settings"}...], "truncated": bool,
    "note": str}."""
    entries: list[dict] = []
    total = 0
    for resource_type in sorted(parsed.get("resources", {})):
        if not _RESOURCE_TYPE.fullmatch(resource_type):
            continue
        bodies = parsed["resources"][resource_type]
        if not isinstance(bodies, dict):
            continue
        for key in sorted(bodies):
            body = bodies[key]
            if not is_created(body, parsed):
                continue
            total += 1
            if len(entries) >= MAX_RESOURCES:
                continue
            module = module_of(body)
            settings = {
                path: _read(body, resource_type, path, parsed, module)
                if isinstance(body, dict)
                else UNKNOWN
                for path in SETTINGS.get(resource_type, ())
            }
            entries.append({"type": resource_type, "name": display_name(key), "settings": settings})
    return {"resources": entries, "truncated": total > len(entries), "note": COVERAGE_NOTE}
