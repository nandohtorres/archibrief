"""What the submitted Terraform declares, as facts the reasoning model can use.

The model never sees the Terraform itself (ADR-0038: submitted code is
untrusted input). Before this summary existed it only saw rule findings,
so it guessed about anything no rule mentioned: in the 2026-10-15 live
run it called Multi-AZ "likely absent" on an instance with
`multi_az = true` (master-list #15b).

So the summary carries facts but leaves no room to write instructions in:

- Only settings on an allowlist, per resource type.
- Values are booleans, numbers, or short identifier-like strings
  (letters, digits, `._:-`, at most 32 characters). Anything else, and
  any reference that can't be resolved statically, becomes "unknown".
- A listed setting the Terraform leaves out is "not set", meaning the
  provider default applies. That's a fact too: it's what stops the model
  guessing.
- Names go through display_name(), the same cleaning as finding text.
- Comments, descriptions, tags and policy documents never appear.
- Resources with count = 0 are left out; the list is capped.
"""

from __future__ import annotations

import re

from backend.lambdas.rule_engine.hcl_eval import is_created, resolve
from backend.shared.terraform_scope import display_name, module_of

NOT_SET = "not set"
UNKNOWN = "unknown"
MAX_RESOURCES = 80
_MAX_STRING = 32
_SAFE_STRING = re.compile(rf"^[A-Za-z0-9._:-]{{1,{_MAX_STRING}}}$")
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


def _first(value: object) -> object:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _read(body: dict, path: str, parsed: dict, module: str) -> object:
    value: object = body
    for part in path.split("."):
        value = _first(value)
        if not isinstance(value, dict) or part not in value:
            return NOT_SET
        value = value[part]
    return _safe_value(resolve(_first(value), parsed, module))


def _safe_value(value: object) -> object:
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "false"):
            return lowered == "true"
        if re.fullmatch(r"-?\d+", value.strip()):
            return int(value.strip())
        if _SAFE_STRING.fullmatch(value) and "${" not in value:
            return value
    return UNKNOWN


def build_resource_summary(parsed: dict) -> dict:
    """{"resources": [{"type", "name", "settings"}...], "truncated": bool}."""
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
                path: _read(body, path, parsed, module) if isinstance(body, dict) else UNKNOWN
                for path in SETTINGS.get(resource_type, ())
            }
            entries.append({"type": resource_type, "name": display_name(key), "settings": settings})
    return {"resources": entries, "truncated": total > len(entries)}
