"""Placing findings on the architecture graph's resources.

Kept apart from the graph builder (backend/lambdas/rule_engine/
architecture.py) because Finalize places the final findings, rule and
model ones, and must not need the HCL parser to do it. A finding goes on
the resources it names; a finding that names none is listed as
account-wide instead of being pinned somewhere arbitrary.
"""

from __future__ import annotations

import copy
import re
from typing import Any

INTERNET_ID = "internet"

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

_DECLARED = re.compile(r'resource\s+"(aws_[a-z0-9_]+)"\s+"([A-Za-z0-9_-]+)"')


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


def _place(nodes: dict[str, dict], findings: list[dict]) -> list[str]:
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
        if str(finding.get("evidence", "")).startswith("Module call '"):
            unplaced.append(finding_id)
            continue
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


def link_findings(graph: dict, findings: list[dict[str, Any]]) -> dict:
    """A copy of `graph` with each finding id on the nodes it names and the
    rest in account_findings. `findings` are finding records (finding_id,
    finding, evidence, risk_impact)."""
    linked = copy.deepcopy(graph)
    nodes = {node["id"]: node for node in linked["nodes"]}
    for node in nodes.values():
        node["findings"] = []
    linked["account_findings"] = _place(nodes, findings)
    return linked
