"""Bounded dependencies; declarations are not effective IAM or proof of key non-use."""

from __future__ import annotations

import json
import re

from backend.shared.hcl_eval import ResolutionBudgetExceeded, is_created, resolve
from backend.shared.terraform_scope import display_name, module_of, scoped_key

_REFERENCE = re.compile(
    r"^\$\{(aws_kms_key|aws_kms_alias|aws_iam_policy|aws_lambda_function|aws_sqs_queue)\.([A-Za-z0-9_-]+)\.[A-Za-z0-9_]+\}$"
)
_ACTION = re.compile(r"^(?:\*|[a-z0-9-]+:[A-Za-z0-9*?]+)$")
_ARN = re.compile(
    r"^arn:aws(?:-us-gov|-cn)?:[a-z0-9-]+:[a-z0-9-]*:[0-9]*:[A-Za-z0-9_./:*?-]{1,200}$"
)
MAX_REFERENCES = 16
MAX_SCAN_NODES = 20000


def _reference(value, parsed, body):
    if not isinstance(value, str) or not value.startswith("${"):
        return None
    try:
        value = resolve(value, parsed, module_of(body), _budget=[8192])
    except ResolutionBudgetExceeded:
        return None
    match = _REFERENCE.fullmatch(value) if isinstance(value, str) else None
    return (match[1], scoped_key(module_of(body), match[2])) if match else None


def boundary_facts(body: dict, parsed: dict) -> dict | None:
    if "permissions_boundary" not in body:
        return None
    result = {
        "status": "unresolved",
        "meaning": "Identity-policy permissions are limited by the boundary; the boundary does not grant permissions.",
    }
    ref = _reference(body["permissions_boundary"], parsed, body)
    if not ref or ref[0] != "aws_iam_policy":
        return result
    result["resource"] = f"{ref[0]}.{display_name(ref[1])}"
    policy = parsed.get("resources", {}).get(ref[0], {}).get(ref[1])
    if not isinstance(policy, dict) or not is_created(policy, parsed):
        return result
    try:
        document = resolve(policy.get("policy"), parsed, module_of(policy), _budget=[32768])
        if isinstance(document, str):
            document = json.loads(document)
    except (ResolutionBudgetExceeded, ValueError):
        return result
    statements = document.get("Statement") if isinstance(document, dict) else None
    statements = [statements] if isinstance(statements, dict) else statements
    if not isinstance(statements, list) or not statements or len(statements) > MAX_REFERENCES:
        return result
    facts = []
    for statement in statements:
        if not isinstance(statement, dict):
            return result
        actions = statement.get("Action")
        resources = statement.get("Resource")
        actions = actions if isinstance(actions, list) else [actions]
        resources = resources if isinstance(resources, list) else [resources]
        if (
            statement.get("Effect") not in {"Allow", "Deny"}
            or any(k in statement for k in ("NotAction", "NotResource", "Condition"))
            or not actions
            or not resources
            or len(actions) > MAX_REFERENCES
            or len(resources) > MAX_REFERENCES
            or any(not isinstance(a, str) or not _ACTION.fullmatch(a) for a in actions)
            or any(not isinstance(r, str) or not (r == "*" or _ARN.fullmatch(r)) for r in resources)
        ):
            return result
        facts.append({"effect": statement["Effect"], "actions": actions, "resources": resources})
    return {**result, "status": "parsed", "statements": facts}


def key_usage(parsed: dict) -> dict[tuple[str, str], dict]:
    """Bound direct and alias-mediated references; never certify an unused key."""
    keys = {}
    resources = parsed.get("resources", {})
    for kind in ("aws_kms_key", "aws_kms_alias"):
        for name, body in resources.get(kind, {}).items():
            if isinstance(body, dict) and is_created(body, parsed):
                keys[(kind, name)] = body
    if not keys:
        return {}
    references = {ref: set() for ref in keys}
    budget = MAX_SCAN_NODES
    for kind, bodies in resources.items():
        for name, body in bodies.items():
            if not isinstance(body, dict) or not is_created(body, parsed):
                continue
            source = (kind, name)
            pending = [body]
            while pending and budget > 0:
                value = pending.pop()
                budget -= 1
                if isinstance(value, dict):
                    pending.extend(value.values())
                elif isinstance(value, list):
                    pending.extend(value)
                elif isinstance(value, str):
                    target = _reference(value, parsed, body)
                    if target in references and source != target:
                        references[target].add(source)
    result = {}
    for key in keys:
        consumers = set()
        pending = list(references[key])
        seen = {key}
        while pending:
            ref = pending.pop()
            if ref in seen:
                continue
            seen.add(ref)
            consumers.add(ref)
            if ref[0] == "aws_kms_alias":
                pending.extend(references.get(ref, ()))
        names = sorted(f"{kind}.{display_name(name)}" for kind, name in consumers)
        result[key] = {
            "declared_consumers": names[:MAX_REFERENCES],
            "declared_consumers_total": len(names),
            "declared_consumers_omitted": max(0, len(names) - MAX_REFERENCES),
            "reference_scan": "partial" if budget <= 0 else "submitted_configuration_only",
            "external_usage": "not_observed",
            "unused_status": "not_established",
        }
    return result


def lambda_invocation_paths(parsed: dict) -> dict[str, dict]:
    """Declared sync/polled and service-async paths, not runtime usage.

    A function permission is not an invoker. Uninspected/external sources stay
    unknown, never a claim that asynchronous invocation cannot occur.
    """
    resources = parsed.get("resources", {})
    functions = {
        name: body
        for name, body in resources.get("aws_lambda_function", {}).items()
        if isinstance(body, dict) and is_created(body, parsed)
    }
    paths = {name: [] for name in functions}

    def add(kind, name, body, value, mode):
        ref = _reference(value, parsed, body)
        if ref and ref[0] == "aws_lambda_function" and ref[1] in paths:
            path = {"resource": f"{kind}.{display_name(name)}", "mode": mode}
            if path not in paths[ref[1]]:
                paths[ref[1]].append(path)

    for kind, attribute, mode in (
        ("aws_lambda_function_url", "function_name", "synchronous_function_url"),
        ("aws_apigatewayv2_integration", "integration_uri", "synchronous_api_gateway"),
        ("aws_lambda_event_source_mapping", "function_name", "polled_event_source"),
        ("aws_sns_topic_subscription", "endpoint", "asynchronous_sns"),
        ("aws_cloudwatch_event_target", "arn", "asynchronous_eventbridge"),
    ):
        for name, body in resources.get(kind, {}).items():
            if not isinstance(body, dict) or not is_created(body, parsed):
                continue
            if (
                kind == "aws_sns_topic_subscription"
                and resolve(body.get("protocol"), parsed, module_of(body)) != "lambda"
            ):
                continue
            add(kind, name, body, body.get(attribute), mode)
    for name, body in resources.get("aws_s3_bucket_notification", {}).items():
        if not isinstance(body, dict) or not is_created(body, parsed):
            continue
        blocks = body.get("lambda_function", [])
        blocks = [blocks] if isinstance(blocks, dict) else blocks
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if isinstance(block, dict):
                add(
                    "aws_s3_bucket_notification",
                    name,
                    body,
                    block.get("lambda_function_arn"),
                    "asynchronous_s3",
                )
    return {
        name: {
            "declared_paths": sorted(found, key=lambda p: p["resource"])[:MAX_REFERENCES],
            "declared_paths_total": len(found),
            "declared_paths_omitted": max(0, len(found) - MAX_REFERENCES),
            "asynchronous_invoker": "declared_sns_subscription"
            if any(p["mode"] == "asynchronous_sns" for p in found)
            else "declared_s3_notification"
            if any(p["mode"] == "asynchronous_s3" for p in found)
            else "declared_eventbridge_target"
            if any(p["mode"] == "asynchronous_eventbridge" for p in found)
            else "not_established",
            "external_invokers": "not_observed",
            "function_dlq_scope": "asynchronous_invocations_only",
        }
        for name, found in paths.items()
    }
