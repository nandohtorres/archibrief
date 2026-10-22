"""POST-FREEZE exploratory probes. Not part of answer_key.json or its metrics.

Written after the frozen run, to pin down why some frozen checks passed or
failed. Each is a real fixture through the real path, asserting the
correct behaviour, so a failure here is a defect, reported separately in
RESULTS.md under "Post-freeze probes".
"""

from __future__ import annotations

import io
import tarfile
from dataclasses import asdict

from backend.lambdas.ingest import handler as ingest_handler
from backend.lambdas.ingest.handler import extract_archive, parse_terraform_files
from backend.lambdas.rule_engine.handler import run_rules

PUBLIC_VIA_DOCUMENT = """
resource "aws_s3_bucket" "anon" {
  bucket = "probe-anon"
}

# Anonymous read written as an aws_iam_policy_document: principals type "*"
# with identifiers ["*"] renders to "Principal": "*".
data "aws_iam_policy_document" "anon_read" {
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::probe-anon/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }
  }
}

resource "aws_s3_bucket_policy" "anon" {
  bucket = aws_s3_bucket.anon.id
  policy = data.aws_iam_policy_document.anon_read.json
}
"""


def _parsed(tmp_path, text: str) -> dict:
    archive = tmp_path / "s.tar"
    with tarfile.open(archive, "w") as tar:
        info = tarfile.TarInfo("main.tf")
        data = text.encode()
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return asdict(
        parse_terraform_files(extract_archive(str(archive), str(tmp_path / "x")))
    )


def test_probe_public_bucket_policy_written_as_policy_document_is_flagged(
    tmp_path,
) -> None:
    """Why F02-D-05 passed: a policy document's principals type "*" is not
    recognised as public at all, so the dropped Condition never mattered."""
    findings = [
        f.finding for f in run_rules(_parsed(tmp_path, PUBLIC_VIA_DOCUMENT), "p")
    ]
    assert any("anon" in f and "allows anyone" in f for f in findings), findings


def test_probe_rejection_reason_for_malformed_hcl(tmp_path, capsys) -> None:
    """Records what F10-M-syntax's rejection reason actually contains."""
    archive = tmp_path / "s.tar"
    text = 'resource "aws_s3_bucket" "x" {\n  bucket = "a" "visible-token-0004"\n}\n'
    with tarfile.open(archive, "w") as tar:
        info = tarfile.TarInfo("main.tf")
        info.size = len(text.encode())
        tar.addfile(info, io.BytesIO(text.encode()))
    result = ingest_handler.handler(
        {
            "workload_brief": "b",
            "review_id": "m",
            "archive_path": str(archive),
            "dest_dir": str(tmp_path / "d"),
        },
        None,
    )
    assert result["status"] == "rejected"
    # The reason is returned to the caller and logged; it must not carry
    # submitted text, nor the server's temp path.
    assert "visible-token-0004" not in result["reason"], result["reason"]
    assert str(tmp_path) not in result["reason"], result["reason"]


def test_probe_unexpected_character_error_does_not_echo_the_line(tmp_path) -> None:
    """The parser error quotes the unexpected token's text, which can run on
    to the end of the file; a synthetic marker after the bad character must
    not come back in the reason."""
    archive = tmp_path / "s.tar"
    text = (
        'resource "aws_s3_bucket" "x" {\n  bucket = x ` SYNTHETIC_SECRET_LINE_0005\n}\n'
    )
    with tarfile.open(archive, "w") as tar:
        info = tarfile.TarInfo("main.tf")
        info.size = len(text.encode())
        tar.addfile(info, io.BytesIO(text.encode()))
    result = ingest_handler.handler(
        {
            "workload_brief": "b",
            "review_id": "m",
            "archive_path": str(archive),
            "dest_dir": str(tmp_path / "d"),
        },
        None,
    )
    assert result["status"] == "rejected"
    assert "SYNTHETIC_SECRET_LINE_0005" not in result["reason"], result["reason"][:400]
