"""The architecture graph drawn in the report.

It must show what the code creates and references, put each finding on
the resource it names (or list it as account-wide), and never invent a
resource or link.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from backend.lambdas.ingest.handler import parse_terraform_files
from backend.lambdas.rule_engine.architecture import (
    INTERNET_ID,
    MAX_NODES,
    build_architecture,
    lane_of,
)
from backend.shared.terraform_scope import MAX_DISPLAY_NAME, display_name

NETWORK = """
resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}
resource "aws_internet_gateway" "gw" {
  vpc_id = aws_vpc.main.id
}
resource "aws_subnet" "public" {
  vpc_id = aws_vpc.main.id
}
resource "aws_security_group" "web" {
  vpc_id = aws_vpc.main.id
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_instance" "proxy" {
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.web.id]
}
resource "aws_s3_bucket" "cardholder-data" {
  bucket = "cardholder-data"
}
resource "aws_s3_bucket_versioning" "cardholder-data" {
  bucket = aws_s3_bucket.cardholder-data.id
  versioning_configuration {
    status = "Enabled"
  }
}
"""


def _parse(tmp_path: Path, text: str) -> dict:
    tf = tmp_path / "main.tf"
    tf.write_text(text, encoding="utf-8")
    return asdict(parse_terraform_files([str(tf)]))


def _finding(finding_id: str, finding: str, evidence: str = "") -> dict:
    return {
        "finding_id": finding_id,
        "finding": finding,
        "evidence": evidence,
        "risk_impact": "",
    }


def _node(graph: dict, node_id: str) -> dict:
    (node,) = [n for n in graph["nodes"] if n["id"] == node_id]
    return node


def _edges(graph: dict) -> set[tuple[str, str]]:
    return {(e["from"], e["to"]) for e in graph["edges"]}


def test_nodes_are_the_created_resources_in_lanes(tmp_path):
    graph = build_architecture(_parse(tmp_path, NETWORK), [])
    ids = {n["id"] for n in graph["nodes"]}
    assert ids == {
        INTERNET_ID,
        "aws_vpc.main",
        "aws_internet_gateway.gw",
        "aws_subnet.public",
        "aws_security_group.web",
        "aws_instance.proxy",
        "aws_s3_bucket.cardholder-data",
    }
    assert _node(graph, "aws_instance.proxy")["lane"] == "compute"
    assert _node(graph, "aws_s3_bucket.cardholder-data")["lane"] == "data"
    assert graph["lanes"] == ["internet", "network", "compute", "data"]
    assert graph["truncated"] is False


def test_edges_are_real_references(tmp_path):
    edges = _edges(build_architecture(_parse(tmp_path, NETWORK), []))
    assert ("aws_instance.proxy", "aws_subnet.public") in edges
    assert ("aws_instance.proxy", "aws_security_group.web") in edges
    assert ("aws_subnet.public", "aws_vpc.main") in edges
    assert ("aws_instance.proxy", "aws_s3_bucket.cardholder-data") not in edges


def test_internet_links_to_gateway_and_open_security_group(tmp_path):
    edges = _edges(build_architecture(_parse(tmp_path, NETWORK), []))
    assert (INTERNET_ID, "aws_internet_gateway.gw") in edges
    assert (INTERNET_ID, "aws_security_group.web") in edges
    assert (INTERNET_ID, "aws_instance.proxy") not in edges


def test_no_internet_node_when_nothing_is_exposed(tmp_path):
    graph = build_architecture(
        _parse(tmp_path, 'resource "aws_s3_bucket" "logs" {}'), []
    )
    assert [n["id"] for n in graph["nodes"]] == ["aws_s3_bucket.logs"]
    assert graph["edges"] == []


def test_configuration_resources_fold_into_their_parent(tmp_path):
    graph = build_architecture(_parse(tmp_path, NETWORK), [])
    assert "aws_s3_bucket_versioning.cardholder-data" not in {
        n["id"] for n in graph["nodes"]
    }
    assert _node(graph, "aws_s3_bucket.cardholder-data")["details"] == [
        "s3 bucket versioning"
    ]


def test_resources_switched_off_are_not_drawn(tmp_path):
    text = 'resource "aws_s3_bucket" "off" {\n  count = 0\n}\nresource "aws_s3_bucket" "on" {}\n'
    graph = build_architecture(_parse(tmp_path, text), [])
    assert [n["id"] for n in graph["nodes"]] == ["aws_s3_bucket.on"]


def test_finding_attaches_to_the_resource_it_quotes(tmp_path):
    findings = [
        _finding("f1", "S3 bucket 'cardholder-data' does not have versioning enabled"),
        _finding("f2", "No aws_cloudtrail resource found in the submitted Terraform"),
    ]
    graph = build_architecture(_parse(tmp_path, NETWORK), findings)
    assert _node(graph, "aws_s3_bucket.cardholder-data")["findings"] == ["f1"]
    assert graph["account_findings"] == ["f2"]


def test_a_plain_name_needs_quotes_to_match(tmp_path):
    # "main" is a common word; unquoted it must not pin the finding on the VPC.
    findings = [_finding("f1", "The main risk is the open proxy port")]
    graph = build_architecture(_parse(tmp_path, NETWORK), findings)
    assert _node(graph, "aws_vpc.main")["findings"] == []


SHARED_NAMES = """
resource "aws_vpc" "rds" {}
resource "aws_security_group" "rds" {
  vpc_id = aws_vpc.rds.id
}
resource "aws_db_subnet_group" "rds" {}
resource "aws_rds_cluster" "production-aurora" {}
resource "aws_rds_cluster" "staging-aurora" {}
"""


def test_shared_name_attaches_only_to_the_hinted_type(tmp_path):
    findings = [_finding("f1", "Security group 'rds' allows SSH or RDP from anywhere")]
    graph = build_architecture(_parse(tmp_path, SHARED_NAMES), findings)
    assert _node(graph, "aws_security_group.rds")["findings"] == ["f1"]
    assert _node(graph, "aws_vpc.rds")["findings"] == []
    assert _node(graph, "aws_db_subnet_group.rds")["findings"] == []


def test_declared_resource_in_evidence_is_exact(tmp_path):
    findings = [
        _finding("f1", "Open ingress", 'resource "aws_security_group" "rds" allows all')
    ]
    graph = build_architecture(_parse(tmp_path, SHARED_NAMES), findings)
    assert _node(graph, "aws_security_group.rds")["findings"] == ["f1"]
    assert _node(graph, "aws_vpc.rds")["findings"] == []


def test_type_phrase_places_unnamed_findings(tmp_path):
    findings = [
        _finding(
            "all", "IAM authentication is not enabled on any of the Aurora clusters"
        ),
        _finding("one", "The production Aurora cluster has no reader in a second AZ"),
    ]
    graph = build_architecture(_parse(tmp_path, SHARED_NAMES), findings)
    assert _node(graph, "aws_rds_cluster.production-aurora")["findings"] == [
        "all",
        "one",
    ]
    assert _node(graph, "aws_rds_cluster.staging-aurora")["findings"] == ["all"]
    assert graph["account_findings"] == []


def test_module_resources_keep_their_path_apart_from_the_name(tmp_path):
    module = tmp_path / "services" / "logs"
    module.mkdir(parents=True)
    (module / "main.tf").write_text(
        'resource "aws_s3_bucket" "access_logs" {}', encoding="utf-8"
    )
    (tmp_path / "main.tf").write_text(
        'resource "aws_s3_bucket" "root" {}\nmodule "logs" { source = "./services/logs" }', encoding="utf-8"
    )
    parsed = asdict(
        parse_terraform_files([str(tmp_path / "main.tf"), str(module / "main.tf")])
    )
    findings = [_finding("f1", "Bucket 'services/logs/access_logs' is not encrypted")]
    graph = build_architecture(parsed, findings)
    (node,) = [n for n in graph["nodes"] if n["name"] == "access_logs"]
    assert node["module"] == "services/logs"
    assert node["findings"] == ["f1"]


def test_graph_is_capped(tmp_path):
    text = "".join(
        f'resource "aws_sqs_queue" "q{i}" {{}}\n' for i in range(MAX_NODES + 5)
    )
    graph = build_architecture(_parse(tmp_path, text), [])
    assert len(graph["nodes"]) == MAX_NODES
    assert graph["truncated"] is True


def test_submitted_names_are_truncated(tmp_path):
    long_name = "a_very_long_name_that_reads_like_an_instruction_to_whoever_sees_it"
    graph = build_architecture(
        _parse(tmp_path, f'resource "aws_s3_bucket" "{long_name}" {{}}'), []
    )
    (node,) = graph["nodes"]
    assert len(node["name"]) <= MAX_DISPLAY_NAME
    assert node["name"] == display_name(long_name)
    other = build_architecture(
        _parse(tmp_path, f'resource "aws_s3_bucket" "{long_name}_other" {{}}'), []
    )
    assert node["name"] != other["nodes"][0]["name"]


def test_omitted_named_resource_is_not_pinned_to_another_resource_of_the_same_type(tmp_path):
    parsed = _parse(tmp_path, 'resource "aws_s3_bucket" "visible" {}')
    findings = [{
        "finding_id": "missing", "finding": "Bucket configuration requires review",
        "evidence": 'resource "aws_s3_bucket" "omitted" has no explicit encryption',
    }]
    graph = build_architecture(parsed, findings)
    assert graph["nodes"][0]["findings"] == []
    assert graph["account_findings"] == ["missing"]
    assert graph["unplaced_scopes"] == {"missing": "resource-not-shown"}


def test_module_scanner_findings_never_attach_by_generic_resource_type(tmp_path):
    graph = build_architecture(_parse(tmp_path, 'resource "aws_security_group" "main" {}'), [{
        "finding_id": "module", "finding": "Module call has a security group issue",
        "evidence": "Module call 'edge_lab': exact resource attribution unavailable",
    }])
    assert graph["nodes"][0]["findings"] == []
    assert graph["unplaced_scopes"] == {"module": "module"}


def test_lane_uses_the_longest_prefix():
    assert lane_of("aws_vpc_endpoint") == "network"
    assert lane_of("aws_cloudwatch_log_group") == "monitoring"
    assert lane_of("aws_something_new") == "data"


def test_rule_engine_returns_the_graph_without_findings(tmp_path):
    from backend.lambdas.rule_engine.handler import handler

    result = handler({"review_id": "r1", "parsed": _parse(tmp_path, NETWORK)}, None)
    graph = result["architecture"]
    assert "aws_instance.proxy" in {n["id"] for n in graph["nodes"]}
    # Findings are placed later, by Finalize, once the model's are in.
    assert all(n["findings"] == [] for n in graph["nodes"])
    assert graph["account_findings"] == []


def test_a_graph_that_fails_to_build_drops_only_the_diagram(tmp_path, monkeypatch):
    import backend.lambdas.rule_engine.handler as handler_module

    def broken(_parsed):
        raise ValueError("boom")

    monkeypatch.setattr(handler_module, "build_graph", broken)
    result = handler_module.handler(
        {"review_id": "r1", "parsed": _parse(tmp_path, NETWORK)}, None
    )
    assert result["architecture"] is None
    assert result["findings"]


def test_link_findings_replaces_earlier_placement(tmp_path):
    from backend.shared.architecture_links import link_findings

    first = build_architecture(
        _parse(tmp_path, NETWORK),
        [_finding("old", "Bucket 'cardholder-data' is public")],
    )
    relinked = link_findings(
        first, [_finding("new", "No aws_cloudtrail resource found")]
    )
    assert _node(relinked, "aws_s3_bucket.cardholder-data")["findings"] == []
    assert relinked["account_findings"] == ["new"]
    # The input graph is left as it was.
    assert _node(first, "aws_s3_bucket.cardholder-data")["findings"] == ["old"]
