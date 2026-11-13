"""A resource the rule engine drops as never created is zero_copy, not cut
by the summary cap (gap found 2026-11-12, AUDIT-ACTION-PLAN Step 5)."""

from tests.backend.lambdas.ingest.test_p0_review_scope import _completed, _run


def _declaration(final: dict, address: str) -> dict:
    return next(d for d in final["declarations"] if d["address"] == address)


def test_resource_the_rule_engine_never_creates_is_zero_copy(tmp_path):
    source = """
provider "aws" { region = "us-east-1" }
variable "on" { default = false }
resource "aws_s3_bucket" "off" { count = var.on }
resource "aws_s3_bucket" "kept" {}
"""
    result, _ = _run(tmp_path, {"main.tf": source})
    assert result["status"] == "parsed"
    final = _completed(result)

    off = _declaration(final, "aws_s3_bucket.off")
    assert off["instances"] == 0
    assert off["in_summary"] is False
    assert (off["category"], off["reason"]) == ("zero_copy", None)

    kept = _declaration(final, "aws_s3_bucket.kept")
    assert (kept["category"], kept["reason"]) == ("reviewed", None)
    assert sum(final["categories"].values()) == final["known_y"] == 2


def test_resolvable_conditional_count_stays_zero_copy(tmp_path):
    source = """
provider "aws" { region = "us-east-1" }
variable "on" { default = false }
resource "aws_s3_bucket" "off" { count = var.on ? 1 : 0 }
"""
    result, _ = _run(tmp_path, {"main.tf": source})
    final = _completed(result)
    off = _declaration(final, "aws_s3_bucket.off")
    assert (off["instances"], off["category"]) == (0, "zero_copy")
