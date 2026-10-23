"""Family 10, evidence-overflow: every bound in the deterministic path, one
below, at and one above, with the decisive defect moved across the bound
by renaming (sort order) or position. See answer_key.json "boundary_cases".

Cases are generated in tmp_path and go through the real archive -> parse
path where the bound lives there. Scanner failures are simulated locally
(subprocess.run patched), never by running anything from a submission.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tarfile
from dataclasses import asdict
from pathlib import Path

import pytest

import backend.lambdas.scan.handler as scan_handler
from backend.lambdas.ingest import handler as ingest_handler
from backend.lambdas.ingest.handler import extract_archive, parse_terraform_files
from backend.lambdas.rule_engine.architecture import (
    MAX_NODES,
    build_architecture,
    build_graph,
)
from backend.lambdas.rule_engine.handler import run_rules
from backend.lambdas.rule_engine.resource_summary import (
    MAX_BACKUP_RULES,
    MAX_RESOURCES,
    build_resource_summary,
)
from backend.lambdas.scan.handler import MAX_RESULTS, scan_files
from backend.shared.archive import (
    MAX_ARCHIVE_MEMBERS,
    MAX_MEMBER_BYTES,
    MAX_UNCOMPRESSED_BYTES,
    IngestRejected,
)
from tests.backend.adversarial.harness import load_answer_key, trivy_path

KEY = load_answer_key()
CONSTANTS = KEY["boundary_cases"]["constants_verified"]


def test_constants_match_the_frozen_answer_key() -> None:
    # The cases below are built from these; if the code's bounds move, the
    # answer key has to be revisited deliberately.
    assert (
        MAX_RESOURCES
        == CONSTANTS["backend/lambdas/rule_engine/resource_summary.py MAX_RESOURCES"]
    )
    assert (
        MAX_BACKUP_RULES
        == CONSTANTS["backend/lambdas/rule_engine/resource_summary.py MAX_BACKUP_RULES"]
    )
    assert (
        MAX_NODES == CONSTANTS["backend/lambdas/rule_engine/architecture.py MAX_NODES"]
    )
    assert MAX_RESULTS == CONSTANTS["backend/lambdas/scan/handler.py MAX_RESULTS"]
    assert (
        MAX_ARCHIVE_MEMBERS
        == CONSTANTS["backend/shared/archive.py MAX_ARCHIVE_MEMBERS"]
    )
    assert MAX_MEMBER_BYTES == CONSTANTS["backend/shared/archive.py MAX_MEMBER_BYTES"]
    assert (
        MAX_UNCOMPRESSED_BYTES
        == CONSTANTS["backend/shared/archive.py MAX_UNCOMPRESSED_BYTES"]
    )


# --- helpers ---------------------------------------------------------------


def _tar(path: Path, members: list[tuple[str, bytes]]) -> Path:
    with tarfile.open(path, "w") as tar:
        for name, data in members:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


def _parse_tf(tmp_path: Path, text: str) -> dict:
    archive = _tar(tmp_path / "s.tar", [("main.tf", text.encode())])
    files = extract_archive(str(archive), str(tmp_path / "x"))
    return asdict(parse_terraform_files(files))


def _safe_db(name: str, public: bool = False) -> str:
    return f'''
resource "aws_db_instance" "{name}" {{
  engine              = "postgres"
  instance_class      = "db.t3.micro"
  storage_encrypted   = true
  multi_az            = true
  publicly_accessible = {str(public).lower()}
}}
'''


# --- resource summary: 79 / 80 / 81 ----------------------------------------


@pytest.mark.parametrize(
    ("total", "decisive", "expect_truncated", "expect_in_summary"),
    [
        pytest.param(79, "zzz_public", False, True, id="F10-S-79"),
        pytest.param(80, "zzz_public", False, True, id="F10-S-80"),
        pytest.param(81, "zzz_public", True, False, id="F10-S-81"),
        pytest.param(81, "aaa_public", True, True, id="F10-S-81-renamed"),
    ],
)
def test_summary_bound(
    tmp_path, total, decisive, expect_truncated, expect_in_summary
) -> None:
    text = "".join(_safe_db(f"db_{i:03d}") for i in range(total - 1)) + _safe_db(
        decisive, True
    )
    parsed = _parse_tf(tmp_path, text)
    summary = build_resource_summary(parsed)
    names = {e["name"] for e in summary["resources"]}
    assert summary["truncated"] is expect_truncated
    assert (decisive in names) is expect_in_summary
    # The rules aren't bounded by the summary: the public database is always found.
    findings = [f.finding for f in run_rules(parsed, "b")]
    assert any(decisive in f and "publicly accessible" in f for f in findings)


# --- architecture graph: 59 / 60 / 61 --------------------------------------


def _log_group(i: int) -> str:
    return (
        f'resource "aws_cloudwatch_log_group" "lg_{i:03d}" {{\n  name = "/lg/{i}"\n}}\n'
    )


OPEN_SG = """
resource "aws_security_group" "zzz_open" {
  name = "open"
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
"""


def test_graph_59_ordinary_nodes(tmp_path) -> None:
    parsed = _parse_tf(tmp_path, "".join(_log_group(i) for i in range(59)))
    graph = build_graph(parsed)
    assert len(graph["nodes"]) == 59
    assert graph["truncated"] is False


@pytest.mark.parametrize(
    ("total", "expect_truncated"),
    [pytest.param(60, False, id="F10-G-60"), pytest.param(61, True, id="F10-G-61")],
)
def test_graph_bound_with_decisive_last(tmp_path, total, expect_truncated) -> None:
    text = "".join(_log_group(i) for i in range(total - 1)) + OPEN_SG
    parsed = _parse_tf(tmp_path, text)
    findings = [f.model_dump(mode="json") for f in run_rules(parsed, "b")]
    graph = build_architecture(parsed, findings)
    assert graph["truncated"] is expect_truncated
    sg_findings = [f["finding_id"] for f in findings if "zzz_open" in f["finding"]]
    assert sg_findings
    placed = {fid for node in graph["nodes"] for fid in node["findings"]}
    listed = set(graph["account_findings"])
    # Whether or not its node fits, the finding is never silently dropped.
    assert all(fid in placed or fid in listed for fid in sg_findings)
    has_edge = {"from": "internet", "to": "aws_security_group.zzz_open"} in graph[
        "edges"
    ]
    assert has_edge is (not expect_truncated)


# --- scanner results: 199 / 200 / 201 (simulated report) ----------------


def _simulated_report(n: int) -> dict:
    """n trusted failing results: n-1 bucket versioning results, then the
    decisive AWS-0180 (public RDS) last."""
    misconfigs = [
        {
            "ID": "AWS-0090",
            "Status": "FAIL",
            "CauseMetadata": {
                "Resource": f"aws_s3_bucket.b_{i:03d}",
                "StartLine": i + 1,
                "EndLine": i + 1,
            },
        }
        for i in range(n - 1)
    ]
    misconfigs.append(
        {
            "ID": "AWS-0180",
            "Status": "FAIL",
            "CauseMetadata": {
                "Resource": "aws_db_instance.ledger",
                "StartLine": 900,
                "EndLine": 905,
            },
        }
    )
    return {"Results": [{"Target": "main.tf", "Misconfigurations": misconfigs}]}


@pytest.mark.parametrize(
    "n",
    [
        pytest.param(199, id="F10-T-199"),
        pytest.param(200, id="F10-T-200"),
        pytest.param(201, id="F10-T-201"),
    ],
)
def test_scanner_result_bound(tmp_path, monkeypatch, n) -> None:
    buckets = "".join(
        f'resource "aws_s3_bucket" "b_{i:03d}" {{}}\n' for i in range(n - 1)
    )
    parsed = _parse_tf(tmp_path, buckets + _safe_db("ledger", public=True))
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()
    (scan_dir / "main.tf").write_text("# placeholder\n", encoding="utf-8")
    monkeypatch.setattr(
        scan_handler, "run_trivy", lambda *_a, **_k: _simulated_report(n)
    )
    scanner = scan_files(str(scan_dir), [str(scan_dir / "main.tf")], sys.executable)
    assert scanner["status"] == "ok"
    kept = len(scanner["results"])
    if n <= MAX_RESULTS:
        assert kept == n
    else:
        # Must disclose that results were dropped...
        assert any("truncat" in k for k in scanner), (
            f"{kept} of {n} kept, no truncation flag: {sorted(scanner)}"
        )
    # ...and the review must still report the public database.
    findings = [f.finding for f in run_rules(parsed, "b", scanner=scanner)]
    assert any("ledger" in f and "publicly accessible" in f for f in findings), (
        f"public RDS lost: {kept} of {n} scanner results kept; Trivy owns rds_public so the own rule stepped aside"
    )


TRIVY = trivy_path()


@pytest.mark.skipif(TRIVY is None, reason="Trivy not installed (set TRIVY_PATH)")
def test_real_trivy_over_the_result_bound(tmp_path) -> None:
    """F10-T-real: offline Trivy on generated Terraform with >200 trusted
    results; the decisive public RDS sits in the last file."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a_buckets.tf").write_text(
        "".join(
            f'resource "aws_s3_bucket" "b_{i:03d}" {{\n  bucket = "b-{i:03d}"\n}}\n'
            for i in range(50)
        ),
        encoding="utf-8",
    )
    (src / "z_db.tf").write_text(_safe_db("ledger", public=True), encoding="utf-8")
    archive = tmp_path / "s.tar"
    with tarfile.open(archive, "w") as tar:
        for p in sorted(src.iterdir()):
            tar.add(p, arcname=p.name)
    files = extract_archive(str(archive), str(tmp_path / "parse"))
    parsed = asdict(parse_terraform_files(sorted(files)))
    scan_list = extract_archive(str(archive), str(tmp_path / "scan"))
    scanner = scan_files(str(tmp_path / "scan"), sorted(scan_list), TRIVY)
    assert scanner["status"] == "ok"
    assert len(scanner["results"]) == MAX_RESULTS, len(scanner["results"])
    findings = [f.finding for f in run_rules(parsed, "b", scanner=scanner)]
    disclosed = any("truncat" in k for k in scanner)
    kept_rds = any("ledger" in f and "publicly accessible" in f for f in findings)
    assert disclosed and kept_rds, (
        f"truncation disclosed: {disclosed}; public RDS finding kept: {kept_rds}"
    )


# --- archive bounds ---------------------------------------------------------


@pytest.mark.parametrize(
    ("count", "accepted"),
    [
        pytest.param(499, True, id="F10-A-499"),
        pytest.param(500, True, id="F10-A-500"),
        pytest.param(501, False, id="F10-A-501"),
    ],
)
def test_archive_member_count(tmp_path, count, accepted) -> None:
    members = [(f"m_{i:03d}.tf", f"# member {i}\n".encode()) for i in range(count - 1)]
    # The decisive defect is the last member.
    members.append(("zz_last.tf", _safe_db("ledger", public=True).encode()))
    archive = _tar(tmp_path / "s.tar", members)
    if accepted:
        files = extract_archive(str(archive), str(tmp_path / "x"))
        assert len(files) == count
        parsed = asdict(parse_terraform_files(sorted(files)))
        assert "ledger" in parsed["resources"]["aws_db_instance"]
    else:
        with pytest.raises(IngestRejected, match="too many members"):
            extract_archive(str(archive), str(tmp_path / "x"))


@pytest.mark.parametrize(
    ("size", "accepted"),
    [
        pytest.param(MAX_MEMBER_BYTES, True, id="F10-A-member-at"),
        pytest.param(MAX_MEMBER_BYTES + 1, False, id="F10-A-member-over"),
    ],
)
def test_archive_member_size(tmp_path, size, accepted) -> None:
    archive = _tar(tmp_path / "s.tar", [("big.tf", b"#" * size)])
    if accepted:
        assert extract_archive(str(archive), str(tmp_path / "x"))
    else:
        with pytest.raises(IngestRejected, match="too large"):
            extract_archive(str(archive), str(tmp_path / "x"))


@pytest.mark.parametrize(
    ("extra", "accepted"),
    [
        pytest.param(0, True, id="F10-A-total-at"),
        pytest.param(1, False, id="F10-A-total-over"),
    ],
)
def test_archive_aggregate_size(tmp_path, extra, accepted) -> None:
    per_member = MAX_MEMBER_BYTES
    count = MAX_UNCOMPRESSED_BYTES // per_member
    members = [(f"p_{i:02d}.tf", b"#" * per_member) for i in range(count)]
    if extra:
        members.append(("tail.tf", b"#" * extra))
    archive = _tar(tmp_path / "s.tar", members)
    if accepted:
        assert len(extract_archive(str(archive), str(tmp_path / "x"))) == count
    else:
        with pytest.raises(IngestRejected, match="uncompressed size"):
            extract_archive(str(archive), str(tmp_path / "x"))


# --- backup plan rules: 10 / 11 --------------------------------------------


def _plan(rules: int) -> str:
    body = "".join(
        f"""
  rule {{
    rule_name         = "r{i}"
    target_vault_name = "v"
    schedule          = "cron(0 {i % 24} * * ? *)"
    lifecycle {{
      delete_after = {1 if i == rules - 1 else 35}
    }}
  }}
"""
        for i in range(rules)
    )
    return f'resource "aws_backup_plan" "p" {{\n  name = "p"\n{body}}}\n'


@pytest.mark.parametrize(
    "rules",
    [pytest.param(10, id="F10-B-10"), pytest.param(11, id="F10-B-11")],
)
def test_backup_rule_bound(tmp_path, rules) -> None:
    summary = build_resource_summary(_parse_tf(tmp_path, _plan(rules)))
    entry = next(e for e in summary["resources"] if e["type"] == "aws_backup_plan")
    shown = len(entry["rules"])
    flagged = any("truncat" in k for k in entry)
    # The decisive rule is the last one (1-day retention).
    assert shown == rules or flagged, (
        f"{shown} of {rules} rules shown, no truncation flag"
    )


# --- scanner failures (simulated) -------------------------------------------


class _FakeS3:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def get_object(self, _key: str) -> bytes:
        return self.data


def _scan_event_bytes(tmp_path: Path) -> bytes:
    return _tar(
        tmp_path / "s.tar", [("main.tf", _safe_db("ledger", public=True).encode())]
    ).read_bytes()


def test_scanner_missing_binary_is_disclosed(tmp_path) -> None:
    """F10-X-missing."""
    parsed = _parse_tf(tmp_path, _safe_db("ledger", public=True))
    scanner = scan_files(str(tmp_path), [], str(tmp_path / "no-such-trivy"))
    assert scanner == {
        "status": "unavailable",
        "tool": "trivy",
        "reason": "scanner_not_installed",
    }
    findings = run_rules(parsed, "b", scanner=scanner)
    assert any(
        f.type.value == "not-observable" and "didn't run" in f.finding for f in findings
    )
    # Every own rule ran, including the one Trivy would otherwise own.
    assert any(
        "ledger" in f.finding and "publicly accessible" in f.finding for f in findings
    )


@pytest.mark.parametrize(
    ("behaviour", "reason"),
    [
        pytest.param("exit", "RuntimeError", id="F10-X-exit"),
        pytest.param("timeout", "timeout", id="F10-X-timeout"),
        pytest.param("garbage", "JSONDecodeError", id="F10-X-garbage"),
    ],
)
def test_scanner_failure_is_unavailable(
    tmp_path, monkeypatch, behaviour, reason
) -> None:
    def fake_run(cmd, **_kwargs):
        if behaviour == "timeout":
            raise subprocess.TimeoutExpired(cmd, 60)
        code, out = (1, b"") if behaviour == "exit" else (0, b"{not json")
        return subprocess.CompletedProcess(cmd, code, stdout=out, stderr=b"")

    monkeypatch.setattr(scan_handler.subprocess, "run", fake_run)
    monkeypatch.setenv("TRIVY_PATH", sys.executable)
    result = scan_handler.handler(
        {"review_id": "b", "report_bucket": "x", "archive_s3_key": "k"},
        None,
        s3_client=_FakeS3(_scan_event_bytes(tmp_path)),
    )
    assert result["status"] == "unavailable"
    assert result["reason"] == reason


# --- deliberately malformed input (labelled separately) ---------------------

MARKER = "SYNTHETIC-SECRET-IN-ERROR-0003"


@pytest.mark.malformed
def test_malformed_hcl_is_rejected_without_echoing_content(tmp_path, capsys) -> None:
    """F10-M-syntax: two adjacent strings are not valid HCL; the parser
    error points at the second one, which holds a synthetic marker."""
    archive = _tar(
        tmp_path / "s.tar",
        [
            (
                "main.tf",
                f'resource "aws_s3_bucket" "x" {{\n  bucket = "a" "{MARKER}"\n}}\n'.encode(),
            )
        ],
    )
    result = ingest_handler.handler(
        {
            "workload_brief": "b",
            "review_id": "m",
            "archive_path": str(archive),
            "dest_dir": str(tmp_path / "d"),
        },
        None,
    )
    logged = capsys.readouterr().out
    assert result["status"] == "rejected"
    assert MARKER not in result["reason"], (
        f"rejection reason echoes file content: {result['reason'][:300]}"
    )
    assert MARKER not in logged, "ingest logged submitted file content"


@pytest.mark.malformed
def test_non_utf8_is_rejected(tmp_path) -> None:
    """F10-M-encoding."""
    archive = _tar(
        tmp_path / "s.tar",
        [("main.tf", b'resource "aws_s3_bucket" "x" {\n  bucket = "\xff\xfe"\n}\n')],
    )
    files = extract_archive(str(archive), str(tmp_path / "x"))
    with pytest.raises(IngestRejected, match="unsupported encoding"):
        parse_terraform_files(files)


def test_answer_key_lists_every_boundary_case() -> None:
    ids = {e["id"] for e in KEY["boundary_cases"]["expectations"]}
    assert len(ids) == len(KEY["boundary_cases"]["expectations"])
    assert {"F10-S-81", "F10-G-61", "F10-T-201", "F10-A-501"} <= ids
    assert json.dumps(KEY)  # loadable and frozen (load_answer_key checked the hash)
