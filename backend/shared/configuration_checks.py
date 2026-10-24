"""Conservative relationships and checks over inspected configuration facts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


def value(bundle, setting, default=None):
    for fact in bundle.get("facts", []):
        if fact["setting"] == setting:
            return fact["value"] if fact["state"] == "known" else default
    return default


def state(bundle, setting):
    return next(
        (f["state"] for f in bundle.get("facts", []) if f["setting"] == setting), "not_inspected"
    )


def target(bundle, setting):
    return next(
        (
            r["target"]
            for r in bundle.get("relations", [])
            if r["setting"] == setting and r["state"] == "known"
        ),
        None,
    )


def derived(bundle, setting, result, *, known=True, basis="declared_relationships"):
    bundle["facts"].append(
        {
            "id": hashlib.sha256(f"{bundle['resource']}:{setting}".encode()).hexdigest()[:16],
            "resource": bundle["resource"],
            "setting": setting,
            "state": "known" if known else "unknown",
            "value": result if known else None,
            "basis": basis,
        }
    )


def enrich_observations(entries):
    bundles = {
        entry["observations"]["resource"]: entry["observations"]
        for entry in entries
        if "observations" in entry
    }
    active = {
        ref: b
        for ref, b in bundles.items()
        if b["creation"] == "declared" and not b.get("truncated") and not b.get("incomplete")
    }
    for ref, bundle in active.items():
        kind = ref.split(".")[0]
        if kind == "aws_subnet":
            explicit = [
                target(b, "route_table_id")
                for r, b in active.items()
                if r.startswith("aws_route_table_association.") and target(b, "subnet_id") == ref
            ]
            vpc = target(bundle, "vpc_id")
            main = [
                target(b, "route_table_id")
                for r, b in active.items()
                if r.startswith("aws_main_route_table_association.")
                and vpc
                and target(b, "vpc_id") == vpc
            ]
            tables = explicit or main
            table = active.get(tables[0]) if len(tables) == 1 else None
            for family, destination in (("ipv4", "0.0.0.0/0"), ("ipv6", "::/0")):
                candidates = []
                if table and vpc and target(table, "vpc_id") == vpc:
                    routes = [table] + [
                        b
                        for r, b in active.items()
                        if r.startswith("aws_route.") and target(b, "route_table_id") == tables[0]
                    ]
                    for route in routes:
                        for fact in route["facts"]:
                            if fact["state"] != "known" or fact["value"] != destination:
                                continue
                            prefix = fact["setting"].rsplit(".", 1)[0]
                            for relationship in route["relations"]:
                                end = relationship.get("target")
                                if (
                                    relationship["state"] != "known"
                                    or not relationship["setting"].startswith(prefix + ".")
                                    or not end
                                ):
                                    continue
                                end_kind = end.split(".")[0]
                                if (
                                    end_kind == "aws_internet_gateway"
                                    and target(active.get(end, {}), "vpc_id") != vpc
                                ):
                                    continue
                                candidates.append(end_kind)
                derived(
                    bundle,
                    "default_route." + family,
                    candidates[0] if len(candidates) == 1 else None,
                    known=len(candidates) == 1,
                )
            derived(
                bundle, "runtime_reachability", None, known=False, basis="packet_path_not_observed"
            )
        if kind == "aws_lambda_event_source_mapping":
            function = active.get(target(bundle, "function_name"), {})
            queue_ref = target(bundle, "event_source_arn")
            queue = (
                active.get(queue_ref, {})
                if queue_ref and queue_ref.startswith("aws_sqs_queue.")
                else {}
            )
            timeout = value(function, "timeout")
            visibility = value(queue, "visibility_timeout_seconds")
            known = type(timeout) is int and type(visibility) is int
            derived(
                bundle,
                "sqs_timeout_relationship",
                "rejected_mapping"
                if known and timeout > visibility
                else "meets_mapping_timeout_constraint"
                if known
                else None,
                known=known,
                basis="aws_lambda_mapping_timeout_constraint",
            )
        if kind == "aws_lambda_function_url":
            function = target(bundle, "function_name")
            actions = {
                value(permission, "action")
                for key, permission in active.items()
                if key.startswith("aws_lambda_permission.")
                and function
                and target(permission, "function_name") == function
                and value(permission, "principal") == "*"
                and value(permission, "public_policy_constraints") == "none_declared"
                and (
                    value(permission, "action") == "lambda:InvokeFunction"
                    or value(permission, "function_url_auth_type") == "NONE"
                )
            }
            both = (
                {"lambda:InvokeFunctionUrl", "lambda:InvokeFunction"} <= actions
                and value(bundle, "authorization_type") == "NONE"
                and value(bundle, "qualifier_scope") == "unqualified"
            )
            derived(
                bundle,
                "public_invocation_permissions",
                "both_actions_declared" if both else None,
                known=both,
                basis="declared_url_auth_and_resource_permissions",
            )
        if kind == "aws_api_gateway_method":
            integrations = [
                b
                for r, b in active.items()
                if r.startswith("aws_api_gateway_integration.")
                and value(b, "http_method")
                and target(b, "rest_api_id")
                and target(b, "rest_api_id") == target(bundle, "rest_api_id")
                and target(b, "resource_id")
                and target(b, "resource_id") == target(bundle, "resource_id")
                and value(b, "http_method") == value(bundle, "http_method")
            ]
            backend = target(integrations[0], "uri") if len(integrations) == 1 else None
            derived(
                bundle,
                "lambda_backend_reference",
                backend,
                known=bool(backend and backend.startswith("aws_lambda_function.")),
            )


@dataclass(frozen=True)
class ConfigurationIssue:
    concern: str
    category: str
    resource: str
    finding: str
    evidence: str
    risk: str
    recommendation: str


def configuration_issues(summary):
    entries = summary.get("resources", [])
    bundles = {
        entry["observations"]["resource"]: entry["observations"]
        for entry in entries
        if "observations" in entry
    }
    issues = []
    for ref, bundle in bundles.items():
        if bundle["creation"] != "declared" or bundle.get("truncated") or bundle.get("incomplete"):
            continue
        kind, name = ref.split(".", 1)
        evidence = f'resource "{kind}" "{name}"'
        azs = [
            f["value"]
            for f in bundle["facts"]
            if f["setting"].startswith("availability_zone[") and f["state"] == "known"
        ]
        all_azs = [f for f in bundle["facts"] if f["setting"].startswith("availability_zone[")]
        if len(azs) >= 2 and len(azs) == len(all_azs) and len(set(azs)) == 1:
            issues.append(
                ConfigurationIssue(
                    "placement_single_az",
                    "availability",
                    ref,
                    f"'{name}' declares multiple instances in one Availability Zone",
                    evidence + f" declares {len(azs)} instance placements in {azs[0]}",
                    "Those declared instances share a zone failure domain; replica count alone does not establish zone redundancy.",
                    "Spread the intended replicas across appropriate Availability Zones and test failover. Placement does not guarantee recovery time.",
                )
            )
        if value(bundle, "sqs_timeout_relationship") == "rejected_mapping":
            issues.append(
                ConfigurationIssue(
                    "invalid_sqs_mapping",
                    "availability",
                    ref,
                    f"SQS mapping '{name}' declares an invalid timeout relationship",
                    evidence + ": function timeout exceeds queue visibility timeout",
                    "Lambda rejects this mapping configuration. This is not evidence of running retries or repeated charges.",
                    "Set queue visibility at least as high as the function timeout, then apply AWS retry-tuning guidance separately.",
                )
            )
        if kind == "aws_s3_bucket_lifecycle_configuration":
            bucket_ref = target(bundle, "bucket")
            versioning = [
                b
                for r, b in bundles.items()
                if r.startswith("aws_s3_bucket_versioning.")
                and bucket_ref
                and target(b, "bucket") == bucket_ref
            ]
            versioned = (
                len(versioning) == 1
                and versioning[0]["creation"] == "declared"
                and value(versioning[0], "versioning_configuration.status") == "Enabled"
            )
            enabled = [
                f["setting"].removesuffix(".status")
                for f in bundle["facts"]
                if f["setting"].endswith(".status")
                and f["value"] == "Enabled"
                and f["state"] == "known"
            ]
            current = any(
                type(value(bundle, prefix + ".expiration.days")) is int
                and value(bundle, prefix + ".filter_scope") == "all_objects"
                for prefix in enabled
            )
            all_absent = bool(enabled) and all(
                state(bundle, prefix + ".noncurrent_expiration_block") == "absent"
                for prefix in enabled
            )
            if versioned and current and all_absent:
                issues.append(
                    ConfigurationIssue(
                        "versioned_retention_gap",
                        "recovery",
                        ref,
                        f"Lifecycle '{name}' expires current objects without noncurrent-version expiration",
                        evidence
                        + ": bucket versioning is Enabled; enabled rules omit noncurrent expiration",
                        "Current-object expiration creates delete markers while old versions remain. This declaration does not establish a physical deletion deadline.",
                        "If the retention requirement covers old versions, configure suitable noncurrent-version expiration and review backups, filters and legal holds separately.",
                    )
                )
    return issues
