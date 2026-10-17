"""The architecture graph drawn in the report, built from the parsed
Terraform without a model.

Nodes are the resources the code creates, grouped into lanes (internet,
edge, network, compute, data, security and identity, monitoring). Edges
are real references in the code: an instance naming its security group,
a cluster naming its subnet group. Small resources that only configure
another one (a bucket's encryption block, a policy attachment) fold into
that resource as a detail instead of becoming a node. An "internet" node
links to what the code exposes: an internet gateway, or a security group
open to 0.0.0.0/0 or ::/0.

Findings attach to the resources they name. A finding that names none
("no aws_cloudtrail resource") is listed as account-wide instead of
being pinned somewhere arbitrary.

Names go through display_name, the same sanitizing the resource summary
uses, so a submitted name can't carry text into the page.
"""

from __future__ import annotations

import json
import re
from typing import Any

from backend.lambdas.rule_engine.hcl_eval import is_created
from backend.lambdas.rule_engine.resource_summary import copies_of
from backend.shared.terraform_scope import display_name, module_of, scoped_key

GRAPH_VERSION = 1
MAX_NODES = 60
INTERNET_ID = "internet"

LANES = ("internet", "edge", "network", "compute", "data", "security", "monitoring")

# Longest prefix wins, so aws_s3_bucket_policy folds before aws_s3 matches.
_LANE_PREFIXES: tuple[tuple[str, str], ...] = (
    ("aws_cloudfront", "edge"),
    ("aws_wafv2", "edge"),
    ("aws_waf", "edge"),
    ("aws_lb", "edge"),
    ("aws_alb", "edge"),
    ("aws_elb", "edge"),
    ("aws_api_gateway", "edge"),
    ("aws_apigatewayv2", "edge"),
    ("aws_route53", "edge"),
    ("aws_acm", "edge"),
    ("aws_vpc", "network"),
    ("aws_subnet", "network"),
    ("aws_internet_gateway", "network"),
    ("aws_nat_gateway", "network"),
    ("aws_eip", "network"),
    ("aws_route", "network"),
    ("aws_security_group", "network"),
    ("aws_network", "network"),
    ("aws_default", "network"),
    ("aws_instance", "compute"),
    ("aws_launch", "compute"),
    ("aws_autoscaling", "compute"),
    ("aws_lambda", "compute"),
    ("aws_ecs", "compute"),
    ("aws_eks", "compute"),
    ("aws_batch", "compute"),
    ("aws_sfn", "compute"),
    ("aws_s3", "data"),
    ("aws_db", "data"),
    ("aws_rds", "data"),
    ("aws_dynamodb", "data"),
    ("aws_elasticache", "data"),
    ("aws_efs", "data"),
    ("aws_backup", "data"),
    ("aws_sqs", "data"),
    ("aws_sns", "data"),
    ("aws_kinesis", "data"),
    ("aws_iam", "security"),
    ("aws_key_pair", "security"),
    ("aws_kms", "security"),
    ("aws_secretsmanager", "security"),
    ("aws_ssm", "security"),
    ("aws_guardduty", "security"),
    ("aws_securityhub", "security"),
    ("aws_cloudtrail", "monitoring"),
    ("aws_cloudwatch", "monitoring"),
    ("aws_flow_log", "monitoring"),
    ("aws_config", "monitoring"),
)

# Resources that only configure another resource: shown as a detail of
# the first resource they reference, not as their own node.
_FOLDED = frozenset(
    {
        "aws_s3_bucket_acl",
        "aws_s3_bucket_cors_configuration",
        "aws_s3_bucket_lifecycle_configuration",
        "aws_s3_bucket_logging",
        "aws_s3_bucket_object_lock_configuration",
        "aws_s3_bucket_ownership_controls",
        "aws_s3_bucket_policy",
        "aws_s3_bucket_public_access_block",
        "aws_s3_bucket_server_side_encryption_configuration",
        "aws_s3_bucket_versioning",
        "aws_s3_bucket_website_configuration",
        "aws_iam_role_policy",
        "aws_iam_role_policy_attachment",
        "aws_iam_policy_attachment",
        "aws_iam_instance_profile",
        "aws_kms_alias",
        "aws_route_table_association",
        "aws_security_group_rule",
        "aws_vpc_security_group_ingress_rule",
        "aws_vpc_security_group_egress_rule",
        "aws_backup_selection",
        "aws_lambda_permission",
        "aws_cloudwatch_log_stream",
        "aws_s3_object",
        "aws_wafv2_web_acl_association",
        "aws_wafv2_web_acl_logging_configuration",
    }
)

# Words that tell which of several same-named resources a finding means
# (the FEC demo names its VPC, security group and subnet group all "rds").
_TYPE_HINTS: tuple[tuple[str, str], ...] = (
    ("security group", "aws_security_group"),
    ("bucket", "aws_s3_bucket"),
    ("instance", "aws_instance"),
    ("rds instance", "aws_db_instance"),
    ("cluster instance", "aws_rds_cluster_instance"),
    ("cluster", "aws_rds_cluster"),
    ("role", "aws_iam_role"),
    ("subnet group", "aws_db_subnet_group"),
    ("subnet", "aws_subnet"),
    ("vpc", "aws_vpc"),
    ("key", "aws_kms_key"),
    ("table", "aws_dynamodb_table"),
    ("function", "aws_lambda_function"),
)

# When a finding names no resource, a type phrase still places it: on the
# one resource of that type ("the EC2 proxy"), on the ones whose name the
# finding uses ("the production Aurora cluster"), or else on all of them
# ("all three Aurora clusters").
_TYPE_PHRASES: tuple[tuple[str, str], ...] = (
    ("aurora cluster", "aws_rds_cluster"),
    ("rds cluster", "aws_rds_cluster"),
    ("ec2", "aws_instance"),
    ("instance", "aws_instance"),
    ("bucket", "aws_s3_bucket"),
    ("iam role", "aws_iam_role"),
    ("role", "aws_iam_role"),
    ("vpc", "aws_vpc"),
    ("security group", "aws_security_group"),
    ("subnet group", "aws_db_subnet_group"),
    ("kms key", "aws_kms_key"),
    ("web acl", "aws_wafv2_web_acl"),
    ("waf", "aws_wafv2_web_acl"),
    ("backup plan", "aws_backup_plan"),
    ("aws backup", "aws_backup_plan"),
    ("lambda", "aws_lambda_function"),
    ("dynamodb", "aws_dynamodb_table"),
)

# A name this distinctive (cg-cardholder-data-bucket, production_aurora_inst)
# can match anywhere in a finding; a plain word like "rds" or "this" only
# when quoted, or it would match every finding that says "RDS".
_DISTINCTIVE = re.compile(r"^(?=.{8,}$)[A-Za-z0-9]+[-_][A-Za-z0-9_-]+$")

# Words too common in resource names to say which one a finding means.
_GENERIC_WORDS = frozenset(
    {
        "aws",
        "this",
        "main",
        "default",
        "rds",
        "aurora",
        "cluster",
        "inst",
        "instance",
        "bucket",
        "role",
        "group",
        "subnet",
        "public",
        "private",
        "security",
        "vpc",
    }
)

_REFERENCE = re.compile(r"\b(aws_[a-z0-9_]+)\.([A-Za-z0-9_-]+)\b")
_DECLARED = re.compile(r'resource\s+"(aws_[a-z0-9_]+)"\s+"([A-Za-z0-9_-]+)"')
_OPEN_CIDR = re.compile(r"(?<![0-9])0\.0\.0\.0/0|::/0")


def lane_of(resource_type: str) -> str:
    best = ""
    lane = "data"
    for prefix, candidate in _LANE_PREFIXES:
        if resource_type.startswith(prefix) and len(prefix) > len(best):
            best, lane = prefix, candidate
    return lane


def _short_type(resource_type: str) -> str:
    return resource_type.removeprefix("aws_").replace("_", " ")


def _created_resources(parsed: dict) -> list[tuple[str, str, dict]]:
    """[(type, key, body)] for every resource the code creates."""
    found = []
    for resource_type in sorted(parsed.get("resources", {})):
        if not resource_type.startswith("aws_"):
            continue
        bodies = parsed["resources"][resource_type]
        if not isinstance(bodies, dict):
            continue
        for key in sorted(bodies):
            body = bodies[key]
            if is_created(body, parsed):
                found.append((resource_type, key, body if isinstance(body, dict) else {}))
    return found


def _references(body: dict, module: str, known: dict[str, str]) -> list[str]:
    """Node ids this body references, in order of appearance."""
    text = json.dumps(body, default=str)
    out: list[str] = []
    for resource_type, name in _REFERENCE.findall(text):
        node_id = known.get(f"{resource_type}.{scoped_key(module, name)}")
        if node_id and node_id not in out:
            out.append(node_id)
    return out


def _finding_text(finding: dict) -> str:
    return " ".join(
        str(finding.get(field) or "") for field in ("finding", "evidence", "risk_impact")
    )


def _mentions(name: str, text: str) -> bool:
    quoted = re.search(rf"['\"`]{re.escape(name)}['\"`]", text) is not None
    if quoted or not _DISTINCTIVE.match(name):
        return quoted
    return re.search(rf"(?<![A-Za-z0-9_-]){re.escape(name)}(?![A-Za-z0-9_-])", text) is not None


def _name_words(name: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", name.lower()) if len(w) > 2} - _GENERIC_WORDS


def _by_type_phrase(
    nodes: dict[str, dict], by_type: dict[str, list[str]], lowered: str
) -> list[str]:
    words = set(re.findall(r"[a-z0-9]+", lowered))
    for phrase, resource_type in _TYPE_PHRASES:
        candidates = by_type.get(resource_type, [])
        if phrase not in lowered or not candidates:
            continue
        named = [n for n in candidates if _name_words(nodes[n]["name"]) & words]
        return named or candidates
    return []


def _link_findings(nodes: dict[str, dict], findings: list[dict]) -> list[str]:
    """Attach finding ids to the nodes they name; return the unplaced ids."""
    by_name: dict[str, list[str]] = {}
    by_type: dict[str, list[str]] = {}
    for node_id, node in nodes.items():
        if node_id == INTERNET_ID:
            continue
        by_name.setdefault(node["name"], []).append(node_id)
        by_type.setdefault(node["type"], []).append(node_id)
    unplaced: list[str] = []
    for finding in findings:
        finding_id = str(finding.get("finding_id", ""))
        text = _finding_text(finding)
        lowered = text.lower()
        hits: set[str] = set()
        declared = _DECLARED.findall(text)
        for resource_type, name in declared:
            hits.update(n for n in by_name.get(name, []) if nodes[n]["type"] == resource_type)
        exact = {name for _type, name in declared}
        for name, node_ids in by_name.items():
            if len(name) < 3 or name in exact or not _mentions(name, text):
                continue
            if len(node_ids) > 1:
                # Several resources share the name: only a type word in the
                # finding says which; without one, guessing would be wrong.
                node_ids = [
                    node_id
                    for node_id in node_ids
                    for phrase, hinted_type in _TYPE_HINTS
                    if phrase in lowered and nodes[node_id]["type"] == hinted_type
                ]
            hits.update(node_ids)
        if not hits:
            hits.update(_by_type_phrase(nodes, by_type, lowered))
        if not hits:
            unplaced.append(finding_id)
            continue
        for node_id in sorted(hits):
            nodes[node_id]["findings"].append(finding_id)
    return unplaced


def build_architecture(parsed: dict, findings: list[dict[str, Any]]) -> dict:
    """{"version", "lanes", "nodes", "edges", "account_findings", "truncated"}.

    `findings` are finding records (dicts with finding_id, finding,
    evidence, risk_impact).
    """
    resources = _created_resources(parsed)
    known: dict[str, str] = {}
    for resource_type, key, _body in resources:
        known[f"{resource_type}.{key}"] = f"{resource_type}.{key}"

    nodes: dict[str, dict] = {}
    folded: list[tuple[str, str, dict]] = []
    truncated = False
    for resource_type, key, body in resources:
        if resource_type in _FOLDED:
            folded.append((resource_type, key, body))
            continue
        if len(nodes) >= MAX_NODES:
            truncated = True
            continue
        node_id = f"{resource_type}.{key}"
        node: dict[str, Any] = {
            "id": node_id,
            "type": resource_type,
            "label": _short_type(resource_type),
            # The name alone; a resource in a module keeps its module path
            # separately, shown smaller.
            "name": display_name(key).rsplit("/", 1)[-1],
            "module": display_name(key).rpartition("/")[0],
            "lane": lane_of(resource_type),
            "details": [],
            "findings": [],
        }
        copies = copies_of(body, parsed, module_of(body))
        if copies is not None:
            node["copies"] = copies
        nodes[node_id] = node

    edges: set[tuple[str, str]] = set()
    for resource_type, key, body in resources:
        source = f"{resource_type}.{key}"
        if source not in nodes:
            continue
        for target in _references(body, module_of(body), known):
            if target in nodes and target != source:
                edges.add((source, target))

    # A folded resource becomes a detail of the first node it references;
    # anything else it references links from that node (a policy
    # attachment ties its role to a policy).
    for resource_type, key, body in folded:
        targets = [t for t in _references(body, module_of(body), known) if t in nodes]
        if not targets:
            continue
        parent, *others = targets
        detail = _short_type(resource_type)
        if detail not in nodes[parent]["details"]:
            nodes[parent]["details"].append(detail)
        for other in others:
            if other != parent:
                edges.add((parent, other))

    exposed = [
        node_id
        for resource_type, key, body in resources
        if (node_id := f"{resource_type}.{key}") in nodes
        and (
            resource_type == "aws_internet_gateway"
            or (
                resource_type == "aws_security_group"
                and _OPEN_CIDR.search(json.dumps(body.get("ingress", ""), default=str))
            )
        )
    ]
    for resource_type, key, body in folded:
        if resource_type in {"aws_security_group_rule", "aws_vpc_security_group_ingress_rule"}:
            text = json.dumps(body, default=str)
            if resource_type == "aws_security_group_rule" and '"egress"' in text:
                continue
            if _OPEN_CIDR.search(text):
                exposed += [
                    t
                    for t in _references(body, module_of(body), known)
                    if t in nodes and nodes[t]["type"] == "aws_security_group"
                ]
    if exposed:
        nodes = {
            INTERNET_ID: {
                "id": INTERNET_ID,
                "type": "internet",
                "label": "internet",
                "name": "Internet",
                "module": "",
                "lane": "internet",
                "details": [],
                "findings": [],
            },
            **nodes,
        }
        edges.update((INTERNET_ID, node_id) for node_id in exposed)

    account_findings = _link_findings(nodes, findings)
    used_lanes = [lane for lane in LANES if any(n["lane"] == lane for n in nodes.values())]
    return {
        "version": GRAPH_VERSION,
        "lanes": used_lanes,
        "nodes": list(nodes.values()),
        "edges": [{"from": a, "to": b} for a, b in sorted(edges)],
        "account_findings": account_findings,
        "truncated": truncated,
    }
