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

from backend.agent.nodes.reason import build_user_content
from backend.lambdas.ingest.handler import parse_terraform_files
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
