"""Lifecycle filter scope: an empty prefix covers the whole bucket (P1 defect B).

Found in the P1 baseline: `filter { prefix = "" }` was labelled
restricted_or_unknown, so the model told the owner a 90-day rule "may apply
only to a subset of objects" when it covers every object.
"""

import tempfile
from dataclasses import asdict
from pathlib import Path

import pytest
from backend.lambdas.ingest.handler import parse_terraform_files
from backend.lambdas.rule_engine.resource_summary import build_resource_summary

_TEMPLATE = """
resource "aws_s3_bucket_lifecycle_configuration" "t" {
  bucket = "x"
  rule {
    id     = "r"
    status = "Enabled"
    %s
    expiration { days = 90 }
  }
}
"""


def _scope(rule_filter: str) -> str:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "main.tf"
        path.write_text(_TEMPLATE % rule_filter, encoding="utf-8")
        parsed = asdict(parse_terraform_files([str(path)]))
    entry = next(
        e
        for e in build_resource_summary(parsed)["resources"]
        if e["type"] == "aws_s3_bucket_lifecycle_configuration"
    )
    facts = {f["setting"]: f["value"] for f in entry["observations"]["facts"]}
    return facts["rule[0].filter_scope"]


@pytest.mark.parametrize(
    "rule_filter",
    ['filter { prefix = "" }', "filter {}", 'prefix = ""', ""],
    ids=["empty-prefix", "empty-filter", "legacy-empty-prefix", "no-filter"],
)
def test_a_filter_that_covers_the_whole_bucket_is_all_objects(rule_filter):
    assert _scope(rule_filter) == "all_objects"


@pytest.mark.parametrize(
    "rule_filter",
    [
        'filter { prefix = "logs/" }',
        'prefix = "logs/"',
        "filter { prefix = var.p }",
        'filter { tag { key = "k" value = "v" } }',
        'filter { and { prefix = "p/" tags = { a = "b" } } }',
        "filter { object_size_greater_than = 100 }",
    ],
    ids=["prefix", "legacy-prefix", "variable-prefix", "tag", "and", "size"],
)
def test_a_filter_that_may_narrow_the_rule_stays_restricted(rule_filter):
    assert _scope(rule_filter) == "restricted_or_unknown"
