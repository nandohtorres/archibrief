"""What the reasoning model is sent must stay small.

Input size drives the model's time. On 2026-10-28 the resource summary grew
to two thirds of a review's input and reviews ran past their timeout, so
these checks fail a change that bloats the summary before a live review
does. Sizes are characters of compact JSON, about four per token.
"""

import json
import tempfile
from dataclasses import asdict
from pathlib import Path

import pytest

from backend.agent.nodes.reason import MAX_RULE_FINDINGS_FOR_MODEL, build_user_content
from backend.lambdas.ingest.handler import parse_terraform_files
from backend.lambdas.rule_engine.handler import run_rules
from backend.lambdas.rule_engine.resource_summary import MAX_RESOURCES, build_resource_summary
from backend.shared.archive import extract_archive

ROOT = Path(__file__).resolve().parents[3]
DEMOS = sorted((ROOT / "frontend/public/demos").glob("*.tar"))
# The largest demo measured 14,681 (2026-10-30).
DEMO_SUMMARY_CHARS = 20_000
# A submission at the resource cap, every resource carrying heavy
# observations, measured 74,169 (2026-10-30): about 18k tokens, what a
# whole review's summary took before the short form.
WORST_SUMMARY_CHARS = 80_000

_DATABASE = """
resource "aws_db_instance" "db_{i}" {{
  engine                  = "postgres"
  instance_class          = "db.r6g.4xlarge"
  storage_encrypted       = false
  multi_az                = false
  publicly_accessible     = true
  backup_retention_period = 1
  vpc_security_group_ids  = [aws_security_group.sg_{i}.id]
}}
resource "aws_security_group" "sg_{i}" {{
  ingress {{
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }}
}}
"""


def _summary_sent(files: list[str]) -> tuple[dict, dict]:
    parsed = json.loads(json.dumps(asdict(parse_terraform_files(files)), default=str))
    summary = build_resource_summary(parsed)
    return summary, build_user_content("brief", [], [], terraform_resources=summary)[
        "terraform_resources"
    ]


def _chars(value: object) -> int:
    return len(json.dumps(value, separators=(",", ":")))


@pytest.mark.parametrize("archive", DEMOS, ids=lambda path: path.stem)
def test_each_demo_sends_a_small_summary(archive, tmp_path):
    summary, sent = _summary_sent(extract_archive(str(archive), str(tmp_path)))
    assert summary["resources"], "the demo parses"
    assert _chars(sent) <= DEMO_SUMMARY_CHARS


def test_a_submission_at_the_cap_still_sends_a_bounded_summary():
    # Each block is a database and its security group: two resources.
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "main.tf"
        path.write_text(
            "".join(_DATABASE.format(i=i) for i in range(MAX_RESOURCES // 2)), encoding="utf-8"
        )
        summary, sent = _summary_sent([str(path)])
    assert len(sent["resources"]) == MAX_RESOURCES
    # Every resource keeps its observations: the budget is large enough
    # for the cap.
    assert summary["analysis_coverage"]["omitted_resources"] == 0
    assert all(entry.get("observations") for entry in sent["resources"])
    assert _chars(sent) <= WORST_SUMMARY_CHARS
    # The short form is what makes the cap affordable.
    assert _chars(sent) < _chars(summary) / 2


# A submission written to break the review: hundreds of resources that
# each trip several rules, with the longest names Terraform allows.
_HOSTILE = """
resource "aws_s3_bucket" "b{i}_{pad}" {{}}
resource "aws_db_instance" "d{i}_{pad}" {{
  publicly_accessible = true
  storage_encrypted   = false
}}
resource "aws_security_group" "g{i}_{pad}" {{
  ingress {{
    from_port   = 0
    to_port     = 65535
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }}
}}
"""
# Everything the model reads except retrieved evidence, which retrieval
# bounds by passage count. About 30k tokens.
WORST_INPUT_CHARS = 120_000


def test_a_submission_built_to_trip_hundreds_of_rules_stays_bounded():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "main.tf"
        path.write_text(
            "".join(_HOSTILE.format(i=i, pad="x" * 50) for i in range(400)), encoding="utf-8"
        )
        parsed = json.loads(
            json.dumps(asdict(parse_terraform_files([str(path)])), default=str)
        )
    rules = [f.model_dump(mode="json") for f in run_rules(parsed, "r")]
    assert len(rules) > 3 * MAX_RULE_FINDINGS_FOR_MODEL, "the submission trips many rules"
    content = build_user_content(
        "brief", rules, [], terraform_resources=build_resource_summary(parsed)
    )
    assert len(content["rule_engine_findings"]) == MAX_RULE_FINDINGS_FOR_MODEL
    assert content["rule_engine_findings_omitted"] == len(rules) - MAX_RULE_FINDINGS_FOR_MODEL
    # Every kind of problem the rules found still reaches the model.
    found = {f["concern"] for f in rules}
    sent = {f["finding"] for f in content["rule_engine_findings"]}
    assert len(found) <= len(sent)
    assert _chars(content["terraform_resources"]) <= WORST_SUMMARY_CHARS
    assert _chars(content) <= WORST_INPUT_CHARS
