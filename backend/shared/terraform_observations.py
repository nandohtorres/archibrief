"""Bounded configuration observations; never evidence of deployed behavior.

Only fixed setting names, validated scalar values and sanitized resource
identities leave this module. Inspected absence is distinct from unknown or
unsupported expressions. An omitted observation is never an absent resource.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Literal, TypedDict

from backend.shared.hcl_eval import is_created, resolve
from backend.shared.terraform_scope import display_name, module_of, scoped_key

VERSION = "terraform-observations@2026-10-23"
MAX_BYTES = 48000
MAX_FACTS = 256
MAX_INSTANCES = 16
DOMAINS = ("placement", "routing", "retention", "backup_selection", "entry_paths")
REGION = re.compile(r"[a-z]{2}(?:-[a-z]+){1,3}-\d")
AZ = re.compile(r"[a-z]{2}(?:-[a-z0-9]+){1,5}-\d[a-z]")
INDEXED = re.compile(r"^\$\{((?:var|local)\.[A-Za-z0-9_-]+)\[count\.index\]\}$")
ELEMENT = re.compile(
    r"^\$\{element\((\[[^\n]{1,1024}\]|(?:var|local)\.[A-Za-z0-9_-]+),\s*count\.index\)\}$"
)
REFERENCE = re.compile(
    r"^\$\{(aws_[a-z0-9_]+)\.([A-Za-z0-9_-]+)\.(?:id|arn|name|identifier|function_name|invoke_arn)\}$"
)
ABSENT = object()
UNRESOLVED = object()


def boolean(value):
    return type(value) is bool


def days(value):
    return type(value) is int and 0 <= value <= 365000


def enumeration(*choices):
    return lambda value: isinstance(value, str) and value in choices


class Fact(TypedDict):
    id: str
    resource: str
    setting: str
    state: Literal["known", "absent", "unknown", "unsupported"]
    value: str | int | float | bool | None
    basis: str


def read(body: object, path: str):
    for part in path.split("."):
        if isinstance(body, list):
            if part.isdigit():
                body = body[int(part)] if int(part) < len(body) else ABSENT
                continue
            if len(body) != 1:
                return UNRESOLVED
            body = body[0]
        if not isinstance(body, dict):
            return ABSENT if body is ABSENT else UNRESOLVED
        if part not in body:
            dynamic = body.get("dynamic", [])
            if isinstance(dynamic, list) and any(
                isinstance(block, dict) and part in block for block in dynamic
            ):
                return UNRESOLVED
            return ABSENT
        body = body[part]
    return body


class ResourceObservations:
    def __init__(self, kind: str, key: str, body: dict, parsed: dict, copies):
        self.kind, self.key, self.body, self.parsed = kind, key, body, parsed
        self.module = module_of(body)
        self.ref = f"{kind}.{display_name(key)}"
        self.facts: list[Fact] = []
        self.relations: list[dict] = []
        self.copies = copies
        self.coverage = dict.fromkeys(DOMAINS, "not_inspected")
        self.omitted_items = 0
        self.unsupported_blocks = False

    def emit(self, setting, value=None, *, state="known", basis="declared_configuration"):
        self.facts.append(
            {
                "id": hashlib.sha256(f"{self.ref}:{setting}".encode()).hexdigest()[:16],
                "resource": self.ref,
                "setting": setting,
                "state": state,
                "value": value,
                "basis": basis,
            }
        )

    def value(self, path, validator, *, setting=None, body=None):
        raw = read(self.body if body is None else body, path)
        name = setting or path
        if raw is ABSENT:
            self.emit(name, state="absent")
            return None
        resolved = resolve(raw, self.parsed, self.module)
        if validator(resolved):
            self.emit(name, resolved)
            return resolved
        self.emit(name, state="unknown")
        return None

    def target(self, raw, kinds=None):
        if not isinstance(raw, str) or len(raw) > 256 or not (match := REFERENCE.fullmatch(raw)):
            return None
        kind, name = match.groups()
        key = scoped_key(self.module, name)
        body = self.parsed.get("resources", {}).get(kind, {}).get(key)
        if (
            (kinds is not None and kind not in kinds)
            or not isinstance(body, dict)
            or not is_created(body, self.parsed)
            or "count" in body
            or "for_each" in body
        ):
            return None
        return f"{kind}.{display_name(key)}"

    def link(self, path, *, body=None, setting=None, kinds=None):
        raw = read(self.body if body is None else body, path)
        target = self.target(raw, kinds)
        state = "known" if target else "absent" if raw is ABSENT else "unknown"
        relation = {
            "source": self.ref,
            "setting": setting or path,
            "target": target,
            "state": state,
            "basis": "direct_submitted_reference",
        }
        self.relations.append(relation)
        return target

    def blocks(self, path):
        dynamic = self.body.get("dynamic", [])
        if isinstance(dynamic, list) and any(
            isinstance(block, dict) and path in block for block in dynamic
        ):
            self.unsupported_blocks = True
            self.emit(path + ".dynamic", state="unsupported", basis="dynamic_blocks_not_expanded")
        value = read(self.body, path)
        if value is UNRESOLVED:
            self.unsupported_blocks = True
            self.emit(path, state="unsupported", basis="dynamic_or_ambiguous_blocks")
            return []
        if isinstance(value, dict):
            return [value]
        if isinstance(value, list):
            self.omitted_items += max(0, len(value) - 32)
        return (
            [block for block in value[:32] if isinstance(block, dict)]
            if isinstance(value, list)
            else []
        )

    def bounded(self, values, limit=32):
        if not isinstance(values, list):
            return []
        self.omitted_items += max(0, len(values) - limit)
        return values[:limit]

    def placement(self):
        provider_key = self.body.get("__provider_binding__")
        if "__provider_binding__" not in self.body:
            provider = self.body.get("provider", "aws")
            if isinstance(provider, str):
                provider = provider.removeprefix("${").removesuffix("}")
                provider_key = scoped_key(self.module, provider)
        provider = self.parsed.get("providers", {}).get(provider_key, {})
        region = resolve(provider.get("region"), self.parsed, module_of(provider))
        valid_region = isinstance(region, str) and REGION.fullmatch(region)
        self.emit(
            "provider.region",
            region if valid_region else None,
            state="known" if valid_region else "unknown",
        )
        self.emit("provider.account", state="unknown", basis="runtime_identity_not_observed")
        regional = self.kind.startswith(
            (
                "aws_instance",
                "aws_subnet",
                "aws_vpc",
                "aws_route",
                "aws_internet_gateway",
                "aws_nat_gateway",
                "aws_egress_only",
                "aws_db_",
                "aws_rds_",
                "aws_ebs_",
                "aws_backup_",
                "aws_sqs_",
                "aws_lambda_",
                "aws_dynamodb_",
                "aws_cloudwatch_",
                "aws_api_gateway",
                "aws_apigatewayv2",
                "aws_sfn_",
                "aws_security_group",
            )
        )
        effective = (
            resolve(self.body["region"], self.parsed, self.module)
            if "region" in self.body
            else region
        )
        valid_effective = regional and isinstance(effective, str) and REGION.fullmatch(effective)
        self.emit(
            "resource.region",
            effective if valid_effective else None,
            state="known" if valid_effective else "unknown",
            basis="resource_override"
            if "region" in self.body
            else "provider_configuration"
            if regional
            else "resource_region_not_established",
        )
        self.coverage["placement"] = "provider_only"
        if self.kind not in {
            "aws_instance",
            "aws_subnet",
            "aws_rds_cluster_instance",
            "aws_ebs_volume",
            "aws_db_instance",
        }:
            return
        self.coverage["placement"] = "inspected"
        if (
            self.copies == "unknown"
            or "for_each" in self.body
            or (isinstance(self.copies, int) and self.copies > MAX_INSTANCES)
        ):
            self.emit(
                "availability_zone", state="unsupported", basis="instance_expansion_not_supported"
            )
            return
        raw = self.body.get("availability_zone", ABSENT)
        count = self.copies if type(self.copies) is int else 1
        for index in range(count):
            path = f"availability_zone[{index}]" if "count" in self.body else "availability_zone"
            if raw is ABSENT:
                self.emit(path, state="absent")
                continue
            value = raw
            if isinstance(raw, str) and (match := INDEXED.fullmatch(raw)):
                values = resolve("${" + match[1] + "}", self.parsed, self.module)
                value = values[index] if isinstance(values, list) and index < len(values) else None
            elif isinstance(raw, str) and (match := ELEMENT.fullmatch(raw)):
                expression = match[1]
                if expression.startswith("["):
                    try:
                        values = json.loads(expression)
                    except ValueError:
                        values = None
                else:
                    values = resolve("${" + expression + "}", self.parsed, self.module)
                value = (
                    values[index % len(values)]
                    if isinstance(values, list) and 0 < len(values) <= MAX_INSTANCES
                    else None
                )
            else:
                value = resolve(value, self.parsed, self.module)
            valid = isinstance(value, str) and AZ.fullmatch(value)
            self.emit(path, value if valid else None, state="known" if valid else "unknown")

    def routing(self):
        paths = {
            "aws_subnet": ("vpc_id",),
            "aws_internet_gateway": ("vpc_id",),
            "aws_nat_gateway": ("subnet_id",),
            "aws_route_table": ("vpc_id",),
            "aws_route_table_association": ("subnet_id", "route_table_id"),
            "aws_main_route_table_association": ("vpc_id", "route_table_id"),
            "aws_instance": ("subnet_id",),
            "aws_route": ("route_table_id",),
            "aws_egress_only_internet_gateway": ("vpc_id",),
            "aws_network_interface": ("subnet_id",),
            "aws_db_subnet_group": (),
            "aws_db_instance": ("db_subnet_group_name",),
            "aws_rds_cluster": ("db_subnet_group_name",),
        }
        if self.kind not in paths:
            return
        self.coverage["routing"] = "direct_references_only"
        for path in paths[self.kind]:
            self.link(path)
        if self.kind == "aws_instance":
            self.value("associate_public_ip_address", boolean)
        routes = (
            self.blocks("route")
            if self.kind == "aws_route_table"
            else [self.body]
            if self.kind == "aws_route"
            else []
        )
        for index, route in enumerate(routes):
            for path in (
                "cidr_block",
                "destination_cidr_block",
                "ipv6_cidr_block",
                "destination_ipv6_cidr_block",
            ):
                self.value(
                    path,
                    enumeration("0.0.0.0/0", "::/0"),
                    body=route,
                    setting=f"route[{index}].{path}",
                )
            for target in (
                "gateway_id",
                "nat_gateway_id",
                "egress_only_gateway_id",
                "transit_gateway_id",
                "network_interface_id",
                "vpc_peering_connection_id",
            ):
                if target in route:
                    self.link(target, body=route, setting=f"route[{index}].{target}")
        for path in ("vpc_security_group_ids", "security_groups", "subnet_ids"):
            raw = self.body.get(path)
            if isinstance(raw, list):
                for index, item in enumerate(self.bounded(raw)):
                    self.link("value", body={"value": item}, setting=f"{path}[{index}]")

    def retention(self):
        fields = {
            "aws_s3_bucket_versioning": (
                ("versioning_configuration.status", enumeration("Enabled", "Suspended")),
            ),
            "aws_dynamodb_table": (
                ("ttl.enabled", boolean),
                ("point_in_time_recovery.enabled", boolean),
            ),
            "aws_cloudwatch_log_group": (("retention_in_days", days),),
            "aws_sfn_state_machine": (("type", enumeration("STANDARD", "EXPRESS")),),
        }
        if self.kind in fields:
            self.coverage["retention"] = "inspected"
            for path, validator in fields[self.kind]:
                self.value(path, validator)
            if self.kind == "aws_dynamodb_table":
                self.emit("ttl.writer", state="unknown", basis="writer_behavior_not_observed")
            if self.kind == "aws_cloudwatch_log_group" and "retention_in_days" not in self.body:
                self.emit(
                    "default_retention_mode", "never_expires", basis="documented_provider_default"
                )
            if self.kind == "aws_sfn_state_machine" and read(self.body, "type") == "STANDARD":
                self.emit(
                    "documented_standard_history_days",
                    90,
                    basis="documented_service_retention_not_physical_deletion_proof",
                )
            if self.kind == "aws_s3_bucket_versioning":
                self.link("bucket", kinds={"aws_s3_bucket"})
        if self.kind == "aws_s3_bucket_replication_configuration":
            self.coverage["retention"] = "direct_references_only"
            self.link("bucket", kinds={"aws_s3_bucket"})
            for index, rule in enumerate(self.blocks("rule")):
                self.value(
                    "status",
                    enumeration("Enabled", "Disabled"),
                    body=rule,
                    setting=f"rule[{index}].status",
                )
                self.link(
                    "destination.bucket",
                    body=rule,
                    setting=f"rule[{index}].destination",
                    kinds={"aws_s3_bucket"},
                )
        if self.kind != "aws_s3_bucket_lifecycle_configuration":
            return
        self.coverage["retention"] = "bounded_rules"
        self.link("bucket", kinds={"aws_s3_bucket"})
        for index, rule in enumerate(self.blocks("rule")):
            prefix = f"rule[{index}]"
            self.value(
                "status", enumeration("Enabled", "Disabled"), body=rule, setting=prefix + ".status"
            )
            filtered = any(key in rule for key in ("prefix", "tag", "and", "dynamic"))
            for block in (
                rule.get("filter", [])
                if isinstance(rule.get("filter"), list)
                else [rule.get("filter", {})]
            ):
                if isinstance(block, dict):
                    filtered |= any(key not in {"__is_block__"} for key in block)
            self.emit(
                prefix + ".filter_scope", "restricted_or_unknown" if filtered else "all_objects"
            )
            for path in (
                "expiration.days",
                "noncurrent_version_expiration.noncurrent_days",
                "noncurrent_version_expiration.newer_noncurrent_versions",
            ):
                self.value(path, days, body=rule, setting=prefix + "." + path)
            self.value(
                "expiration.expired_object_delete_marker",
                boolean,
                body=rule,
                setting=prefix + ".expiration.expired_object_delete_marker",
            )

    def backups(self):
        if self.kind in {"aws_db_instance", "aws_rds_cluster"}:
            self.coverage["backup_selection"] = "native_retention_only"
            self.value("backup_retention_period", days)
        if self.kind == "aws_backup_selection":
            self.coverage["backup_selection"] = "explicit_references_only"
            self.link("plan_id", kinds={"aws_backup_plan"})
            for field in ("resources", "not_resources"):
                values = self.body.get(field)
                if isinstance(values, list):
                    for index, value in enumerate(self.bounded(values)):
                        self.link("value", body={"value": value}, setting=f"{field}[{index}]")
                elif field in self.body:
                    self.emit(field, state="unknown")
                else:
                    self.emit(field, state="absent")
            if self.body.get("selection_tag") or self.body.get("condition"):
                self.tag_selection()
        if self.kind != "aws_backup_plan":
            return
        self.coverage["backup_selection"] = "bounded_rules"
        for index, rule in enumerate(self.blocks("rule")):
            prefix = f"rule[{index}]"
            self.link(
                "target_vault_name",
                body=rule,
                setting=prefix + ".source_vault",
                kinds={"aws_backup_vault"},
            )
            self.value(
                "lifecycle.delete_after", days, body=rule, setting=prefix + ".source_retention_days"
            )
            for copy_index, copy in enumerate(self.bounded(rule.get("copy_action"), 16)):
                if not isinstance(copy, dict):
                    continue
                path = prefix + f".copy[{copy_index}]"
                self.link(
                    "destination_vault_arn",
                    body=copy,
                    setting=path + ".destination",
                    kinds={"aws_backup_vault"},
                )
                self.value(
                    "lifecycle.delete_after",
                    days,
                    body=copy,
                    setting=path + ".explicit_retention_days",
                )
                if read(copy, "lifecycle.delete_after") is ABSENT:
                    source = resolve(read(rule, "lifecycle.delete_after"), self.parsed, self.module)
                    self.emit(
                        path + ".derived_retention_days",
                        source if days(source) else None,
                        state="known" if days(source) else "unknown",
                        basis="aws_backup_source_retention_inheritance",
                    )

    def tag_selection(self):
        """Bounded exact tag predicates, not proof a backup job will run."""
        predicates = []
        mode = "or"
        supported = not any(key in self.body for key in ("resources", "not_resources"))
        if self.body.get("condition"):
            mode = "and"
            supported &= not bool(self.body.get("selection_tag"))
            condition = read(self.body, "condition")
            condition = (
                condition[0] if isinstance(condition, list) and len(condition) == 1 else condition
            )
            if isinstance(condition, dict):
                supported &= not any(
                    key not in {"__is_block__", "string_equals"} for key in condition
                )
                predicates = condition.get("string_equals", [])
            else:
                supported = False
        else:
            predicates = self.body.get("selection_tag", [])
        supported &= isinstance(predicates, list) and 0 < len(predicates) <= 30
        checks = []
        for predicate in predicates[:30] if isinstance(predicates, list) else []:
            if not isinstance(predicate, dict):
                supported = False
                continue
            key = resolve(predicate.get("key"), self.parsed, self.module)
            val = resolve(predicate.get("value"), self.parsed, self.module)
            exact = mode == "and" or predicate.get("type") == "STRINGEQUALS"
            if mode == "and" and isinstance(key, str) and key.startswith("aws:ResourceTag/"):
                key = key.removeprefix("aws:ResourceTag/")
            elif mode == "and":
                supported = False
            if not exact or not all(
                isinstance(item, str) and len(item) <= 128 and "${" not in item
                for item in (key, val)
            ):
                supported = False
            checks.append((key, val))
        self.emit(
            "tag_selection",
            "bounded_exact_predicates" if supported else None,
            state="known" if supported else "unsupported",
            basis="declared_tag_predicates_only",
        )
        if not supported:
            return
        candidates = []
        for kind in (
            "aws_db_instance",
            "aws_rds_cluster",
            "aws_s3_bucket",
            "aws_dynamodb_table",
            "aws_ebs_volume",
        ):
            for key, body in sorted(self.parsed.get("resources", {}).get(kind, {}).items()):
                if (
                    isinstance(body, dict)
                    and module_of(body) == self.module
                    and is_created(body, self.parsed)
                ):
                    candidates.append((kind, key, body))
        self.omitted_items += max(0, len(candidates) - 32)
        for kind, key, body in candidates[:32]:
            tags = resolve(body.get("tags", {}), self.parsed, self.module)
            resolved = (
                isinstance(tags, dict)
                and all(
                    tag in tags and isinstance(tags[tag], str) and "${" not in tags[tag]
                    for tag, _val in checks
                )
                and "count" not in body
                and "for_each" not in body
            )
            matches = [tags[tag] == val for tag, val in checks] if resolved else []
            self.relations.append(
                {
                    "source": self.ref,
                    "setting": "tag_selector_match",
                    "target": f"{kind}.{display_name(key)}",
                    "state": "known" if resolved else "unknown",
                    "matches_selector": (all(matches) if mode == "and" else any(matches))
                    if resolved
                    else None,
                    "basis": "declared_tags_not_service_opt_in_or_backup_execution",
                }
            )

    def entry_paths(self):
        fields = {
            "aws_lambda_function_url": (("authorization_type", enumeration("NONE", "AWS_IAM")),),
            "aws_api_gateway_method": (
                ("authorization", enumeration("NONE", "AWS_IAM", "CUSTOM", "COGNITO_USER_POOLS")),
                ("api_key_required", boolean),
                (
                    "http_method",
                    enumeration("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "ANY"),
                ),
            ),
            "aws_api_gateway_integration": (
                (
                    "http_method",
                    enumeration("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "ANY"),
                ),
            ),
            "aws_apigatewayv2_route": (
                ("authorization_type", enumeration("NONE", "AWS_IAM", "JWT", "CUSTOM")),
            ),
            "aws_lambda_function": (("timeout", days),),
            "aws_sqs_queue": (("visibility_timeout_seconds", days),),
            "aws_lambda_permission": (
                ("action", enumeration("lambda:InvokeFunction", "lambda:InvokeFunctionUrl")),
                ("principal", enumeration("*", "apigateway.amazonaws.com")),
                ("function_url_auth_type", enumeration("NONE", "AWS_IAM")),
            ),
        }
        relationships = {
            "aws_lambda_function_url": ("function_name",),
            "aws_lambda_permission": ("function_name",),
            "aws_api_gateway_method": ("rest_api_id", "resource_id", "authorizer_id"),
            "aws_api_gateway_integration": ("rest_api_id", "resource_id", "uri"),
            "aws_lambda_event_source_mapping": ("function_name", "event_source_arn"),
            "aws_apigatewayv2_route": ("api_id", "authorizer_id"),
        }
        if self.kind not in fields and self.kind not in relationships:
            return
        self.coverage["entry_paths"] = "declared_auth_and_direct_references"
        for path, validator in fields.get(self.kind, ()):
            self.value(path, validator)
        for path in relationships.get(self.kind, ()):
            self.link(path)
        if self.kind == "aws_lambda_function_url":
            self.emit(
                "qualifier_scope",
                "restricted_or_unknown" if "qualifier" in self.body else "unqualified",
            )
        if self.kind == "aws_lambda_permission":
            constrained = any(
                field in self.body
                for field in (
                    "source_arn",
                    "source_account",
                    "principal_org_id",
                    "event_source_token",
                    "qualifier",
                )
            )
            self.emit(
                "public_policy_constraints",
                "restricted_or_unknown" if constrained else "none_declared",
            )
        if self.kind in {
            "aws_lambda_function_url",
            "aws_api_gateway_method",
            "aws_apigatewayv2_route",
        }:
            self.emit(
                "runtime_invocation",
                state="unknown",
                basis="effective_policy_and_runtime_not_observed",
            )

    def build(self):
        self.placement()
        self.routing()
        self.retention()
        self.backups()
        self.entry_paths()
        return {
            "version": VERSION,
            "resource": self.ref,
            "creation": "conditional" if self.copies == "unknown" else "declared",
            "source": {
                "kind": "submitted_resource_block",
                "module": display_name(self.module) if self.module else "root",
                "line": None,
            },
            "facts": self.facts,
            "relations": self.relations,
            "coverage": self.coverage,
            "omitted_items": self.omitted_items,
            "truncated": bool(self.omitted_items),
            "incomplete": self.unsupported_blocks,
        }


@dataclass
class ObservationBudget:
    bytes_used: int = 0
    facts_emitted: int = 0
    omitted_resources: int = 0
    omitted_items: int = 0
    incomplete_resources: int = 0

    def admit(self, bundle):
        size = len(json.dumps(bundle, separators=(",", ":")).encode("utf-8"))
        count = len(bundle["facts"])
        if self.bytes_used + size > MAX_BYTES or self.facts_emitted + count > MAX_FACTS:
            self.omitted_resources += 1
            return None
        self.bytes_used += size
        self.facts_emitted += count
        self.omitted_items += bundle.get("omitted_items", 0)
        self.incomplete_resources += bool(bundle.get("incomplete"))
        return bundle

    def manifest(self):
        return {
            "version": VERSION,
            "scope": "submitted_configuration_only",
            "domains": list(DOMAINS),
            "emitted_bytes": self.bytes_used,
            "facts_emitted": self.facts_emitted,
            "omitted_resources": self.omitted_resources,
            "truncated": bool(self.omitted_resources or self.omitted_items),
            "omitted_items": self.omitted_items,
            "incomplete_resources": self.incomplete_resources,
            "runtime_verified": False,
            "token_count": "not_measured",
        }
