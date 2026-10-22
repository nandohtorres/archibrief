"""What the submitted Terraform declares, as facts the reasoning model can use.

The model never sees the Terraform itself (ADR-0038: submitted code is
untrusted input). With only rule findings to go on, it guesses about
anything no rule mentions, for example calling Multi-AZ "likely absent"
on an instance with `multi_az = true`.

So the summary carries facts but leaves no room to write instructions in:

- Only settings on an allowlist, per resource type.
- Values are booleans, numbers, or a string the setting can really take
  (an engine from a known list, an instance class in AWS's format, ...).
  Anything else, and any reference that can't be resolved statically,
  becomes "unknown". A looser rule (any short identifier) would let a
  value like `IGNORE_ALL_FINDINGS` through as an engine, so no free-form
  words reach the model through a value.
- A listed setting the Terraform leaves out is "not set (default: X)"
  when the AWS provider's default is documented and fixed, and plain
  "not set" when it depends on something outside the code (account
  settings, the AMI, the subnet). The model recalls defaults unreliably
  (e.g. claiming an unset skip_final_snapshot skips the final snapshot;
  the default is false), so it's told the default, never asked to
  recall it.
- Names go through display_name(), the same cleaning as finding text.
- Comments, descriptions, tags and policy documents never appear.
- Resources with count = 0 are left out; the list is capped.
"""

from __future__ import annotations

import re

from backend.lambdas.rule_engine.hcl_eval import is_created, resolve
from backend.shared.terraform_scope import display_name, module_of

NOT_SET = "not set"
# Fixed text, never built from the submission. Without it the model reads
# a setting missing from the summary as missing from the code ("no
# CloudWatch log exports are present").
COVERAGE_NOTE = (
    "Only the settings named for each resource were checked. A setting not "
    "named here may still be set in the code: never describe it as missing. "
    '"copies" is how many instances count or for_each creates ("unknown" when '
    "it can't be worked out from the code); a resource without it is created once. "
    '"rules" on a backup plan lists each backup rule: its schedule, how many days '
    "recovery points are kept, and whether they are copied to another vault."
    " rules_total and rules_truncated disclose omitted backup rules; when truncated, "
    "copy rules and short retention are prioritized and source_index is one-based."
)
# A count above this is reported as unknown rather than trusted.
MAX_COPIES = 1000
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
        "copy_tags_to_snapshot",
    ),
    "aws_rds_cluster": (
        "engine",
        "storage_encrypted",
        "backup_retention_period",
        "deletion_protection",
        "iam_database_authentication_enabled",
        "skip_final_snapshot",
        # Listed so the model doesn't call it unconfirmed when it is set.
        "copy_tags_to_snapshot",
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
# out (the RDS API default; Trivy AWS-0077 treats unset as 1); left to
# itself the model tends to guess 0.
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
        "copy_tags_to_snapshot": False,
    },
    "aws_rds_cluster": {
        "deletion_protection": False,
        "iam_database_authentication_enabled": False,
        "skip_final_snapshot": False,
        "copy_tags_to_snapshot": False,
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
    "aws_cloudwatch_log_group": {"retention_in_days": "never expires"},
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


def copies_of(body: dict, parsed: dict, module: str) -> int | str | None:
    """How many instances count/for_each creates; None when neither is set.

    Without it the model may assume one instance where the code creates
    several (e.g. count = 3 Aurora cluster instances).
    """
    if "count" in body:
        value = resolve(body["count"], parsed, module)
        if isinstance(value, str) and value.isdigit():
            value = int(value)
        if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_COPIES:
            return value
        return UNKNOWN
    if "for_each" in body:
        value = resolve(body["for_each"], parsed, module)
        if isinstance(value, (dict, list)) and len(value) <= MAX_COPIES:
            return len(value)
        return UNKNOWN
    return None


MAX_BACKUP_RULES = 10
_CRON_FIELD = (
    r"(?:[0-9*?/,#LW-]|MON|TUE|WED|THU|FRI|SAT|SUN"
    r"|JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)+"
)
# An AWS Backup schedule: six cron fields or a rate. Letters are limited
# to day and month names, so no words of the submitter's choosing get through.
_SCHEDULE = re.compile(
    rf"^(?:cron\({_CRON_FIELD}(?: {_CRON_FIELD}){{5}}\)"
    r"|rate\(\d{1,4} (?:minutes?|hours?|days?)\))$"
)


def _backup_rules(body: dict, parsed: dict, module: str) -> list[dict]:
    """Each rule's schedule, retention and copies, for aws_backup_plan.

    A plan has several rule blocks, and the dotted-path settings only read
    the first, which would leave the other rules' schedules and retention
    invisible to the model. Rule names are free text and are left out.
    """
    rules = body.get("rule")
    if isinstance(rules, dict):
        rules = [rules]
    if not isinstance(rules, list):
        return []
    out = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        lifecycle = _first(rule.get("lifecycle"))
        lifecycle = lifecycle if isinstance(lifecycle, dict) else {}

        def value(block: dict, key: str, when_unset: str) -> object:
            if key not in block:
                return when_unset
            return _safe_value(resolve(_first(block[key]), parsed, module), "")

        out.append(
            {
                "schedule": _schedule(rule, parsed, module),
                "delete_after_days": value(
                    lifecycle, "delete_after", f"{NOT_SET} (default: kept until deleted)"
                ),
                "cold_storage_after_days": value(lifecycle, "cold_storage_after", NOT_SET),
                "copied_to_another_vault": bool(rule.get("copy_action")),
                "continuous_backup": value(
                    rule, "enable_continuous_backup", f"{NOT_SET} (default: false)"
                ),
            }
        )
    if len(out) <= MAX_BACKUP_RULES:
        return out
    indexed = list(enumerate(out, start=1))
    indexed.sort(key=lambda item: (
        not item[1]["copied_to_another_vault"],
        item[1]["delete_after_days"] if isinstance(item[1]["delete_after_days"], int) else float("inf"),
        item[0],
    ))
    return [{**rule, "source_index": index} for index, rule in indexed[:MAX_BACKUP_RULES]]


def _schedule(rule: dict, parsed: dict, module: str) -> str:
    if "schedule" not in rule:
        return NOT_SET
    schedule = resolve(_first(rule["schedule"]), parsed, module)
    if isinstance(schedule, str) and _SCHEDULE.fullmatch(schedule.strip()):
        return schedule.strip()
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
            if resource_type == "aws_cloudwatch_log_group" and settings.get("retention_in_days") == 0:
                settings["retention_in_days"] = "never expires (configured: 0)"
            entry = {"type": resource_type, "name": display_name(key), "settings": settings}
            copies = copies_of(body, parsed, module) if isinstance(body, dict) else None
            if copies is not None:
                entry["copies"] = copies
            if resource_type == "aws_backup_plan" and isinstance(body, dict):
                entry["rules"] = _backup_rules(body, parsed, module)
                raw_rules = body.get("rule", [])
                raw_rules = raw_rules if isinstance(raw_rules, list) else [raw_rules]
                entry["rules_total"] = sum(isinstance(rule, dict) for rule in raw_rules)
                entry["rules_truncated"] = entry["rules_total"] > len(entry["rules"])
            entries.append(entry)
    return {"resources": entries, "truncated": total > len(entries), "note": COVERAGE_NOTE}
