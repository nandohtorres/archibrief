import io
import os
import tarfile
from pathlib import Path

import pytest

from backend.lambdas.scan import handler as scan
from backend.lambdas.scan.handler import (
    NEUTRALIZED_SOURCE,
    neutralize_remote_sources,
    trusted_results,
)


def _write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_remote_and_escaping_module_sources_are_neutralized(tmp_path):
    main = _write(
        tmp_path / "main.tf",
        'module "registry" {\n  source  = "terraform-aws-modules/vpc/aws"\n}\n'
        'module "git" {\n  source = "git::https://attacker.example/x.git" # comment\n}\n'
        'module "s3" {\n  source = "s3::https://s3.amazonaws.com/bucket/key.zip"\n}\n'
        'module "escape" {\n  source = "../../../etc"\n}\n'
        'module "local" {\n  source = "./child"\n}\n',
    )
    child = _write(tmp_path / "child" / "main.tf", "")

    changed = neutralize_remote_sources([main, child], str(tmp_path))

    text = Path(main).read_text(encoding="utf-8")
    assert changed == 4
    assert text.count(NEUTRALIZED_SOURCE) == 4
    assert 'source = "./child"' in text
    for remote in ("terraform-aws-modules", "attacker.example", "s3::", "../../../etc"):
        assert remote not in text
    assert "# comment" in text  # rest of the line kept, so line numbers don't move


def test_module_source_rewriting_is_structural_and_preserves_provider_sources(tmp_path):
    text = (
        'terraform {\n required_providers {\n aws = {\n source = "hashicorp/aws"\n }\n }\n}\n'
        'locals {\n payload = <<DOC\nmodule "fake" { source = "https://example.invalid/fake" }\nDOC\n}\n'
        'module "one" { source = "git::https://example.invalid/one.git" }\n'
        'module "escaped" { source = "\\u002e\\u002e/escape" }\n'
    )
    path = _write(tmp_path / "main.tf", text)
    assert neutralize_remote_sources([path], str(tmp_path)) == 2
    rewritten = Path(path).read_text(encoding="utf-8")
    assert 'source = "hashicorp/aws"' in rewritten
    assert 'module "fake" { source = "https://example.invalid/fake" }' in rewritten
    assert "example.invalid/one.git" not in rewritten
    assert rewritten.count(NEUTRALIZED_SOURCE) == 2
    assert rewritten.count("\n") == text.count("\n")


def test_malformed_module_source_fails_before_the_scanner_runs(tmp_path, monkeypatch):
    path = _write(tmp_path / "main.tf", 'module "broken" { source = "unterminated')
    invoked = []
    monkeypatch.setattr(scan, "run_trivy", lambda *_a, **_k: invoked.append(True))
    with pytest.raises(ValueError, match="unsupported HCL"):
        scan.scan_files(str(tmp_path), [path], trivy_path=__file__)
    assert invoked == []


def test_trivy_runs_without_aws_credentials_or_network(tmp_path, monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAEXAMPLE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "token")

    env = scan._trivy_env(str(tmp_path))

    assert not any(key.startswith("AWS_") for key in env)
    assert env["HTTPS_PROXY"] == env["HTTP_PROXY"] == "http://127.0.0.1:9"
    assert env["NO_PROXY"] == ""


def _report(target: str, items: list[dict]) -> dict:
    return {"Results": [{"Target": target, "Misconfigurations": items}]}


def _item(check_id: str, resource: str, status: str = "FAIL", line: int = 3) -> dict:
    return {
        "ID": check_id,
        "Status": status,
        "CauseMetadata": {"Resource": resource, "StartLine": line, "EndLine": line + 2},
    }


def test_only_trusted_failing_checks_are_kept(tmp_path):
    files = [_write(tmp_path / "main.tf", "")]
    report = _report(
        "main.tf",
        [
            _item("AWS-0107", "aws_security_group.app"),
            _item("AWS-0132", "aws_s3_bucket.data"),  # CMK noise, not trusted
            _item("AWS-0086", "aws_s3_bucket.data", status="PASS"),
        ],
    )

    results = trusted_results(report, str(tmp_path), files)

    assert results == [
        {
            "check_id": "AWS-0107",
            "resource_type": "aws_security_group",
            "resource_key": "app",
            "file": "main.tf",
            "start_line": 3,
            "end_line": 5,
        }
    ]


def test_results_are_module_scoped_and_unsafe_names_dropped(tmp_path):
    files = [
        _write(tmp_path / "modules" / "a" / "main.tf", ""),
        _write(tmp_path / "modules" / "b" / "main.tf", ""),
    ]
    report = {
        "Results": [
            {
                "Target": "modules/b/main.tf",
                "Misconfigurations": [_item("AWS-0090", "aws_s3_bucket.logs")],
            },
            {
                "Target": "modules/a/main.tf",
                "Misconfigurations": [
                    _item("AWS-0090", 'aws_s3_bucket.bad"name'),
                    _item("AWS-0090", "module.x.aws_s3_bucket.inner"),
                ],
            },
        ]
    }

    results = trusted_results(report, str(tmp_path), files)

    assert [r["resource_key"] for r in results] == ["b/logs", "a/inner"]


def test_module_only_cause_is_reported_at_module_scope_without_a_phantom_resource(tmp_path):
    from backend.lambdas.rule_engine.handler import run_rules

    files = [_write(tmp_path / "main.tf", "")]
    results = trusted_results(_report("main.tf", [_item("AWS-0107", "module.edge_lab")]), str(tmp_path), files)
    assert results[0]["scope"] == "module"
    assert results[0]["resource_key"] == "edge_lab"
    findings = run_rules({"resources": {}}, "module-cause", {"status": "ok", "results": results})
    relevant = [f for f in findings if "edge_lab" in f.finding]
    assert relevant
    assert all('resource "module"' not in f.evidence for f in relevant)
    assert any("attribution" in f.evidence for f in relevant)
    assert any(f.type.value == "not-observable" and "attribut" in f.finding for f in findings)


def test_counted_and_for_each_resources_keep_their_results(tmp_path):
    # Trivy reports count/for_each instances as name[0] / name["key"].
    # These were dropped as unsafe names, so e.g. FEC's publicly
    # accessible Aurora instances (count = 3) produced no finding.
    files = [_write(tmp_path / "main.tf", "")]
    report = {
        "Results": [
            {
                "Target": "main.tf",
                "Misconfigurations": [
                    _item("AWS-0180", "aws_rds_cluster_instance.prod[0]"),
                    _item("AWS-0180", "aws_rds_cluster_instance.prod[1]"),
                    _item("AWS-0090", 'aws_s3_bucket.logs["eu"]'),
                    _item("AWS-0090", 'aws_s3_bucket.bad"name[0]'),
                ],
            }
        ]
    }

    results = trusted_results(report, str(tmp_path), files)

    assert [r["resource_key"] for r in results] == ["prod", "prod", "logs"]


def test_results_are_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(scan, "MAX_RESULTS", 3)
    files = [_write(tmp_path / "main.tf", "")]
    report = _report(
        "main.tf", [_item("AWS-0090", f"aws_s3_bucket.b{i}") for i in range(10)]
    )

    assert len(trusted_results(report, str(tmp_path), files)) == 3


def test_partial_scan_discloses_totals_and_falls_back_for_omitted_concerns(tmp_path, monkeypatch):
    from backend.lambdas.rule_engine.handler import run_rules

    monkeypatch.setattr(scan, "MAX_RESULTS", 3)
    files = [_write(tmp_path / "main.tf", "")]
    report = _report("main.tf", [
        *[_item("AWS-0090", f"aws_s3_bucket.b{i}") for i in range(4)],
        _item("AWS-0180", "aws_db_instance.ledger"),
    ])
    monkeypatch.setattr(scan, "run_trivy", lambda *_a, **_k: report)
    result = scan.scan_files(str(tmp_path), files, trivy_path=__file__)
    assert result["truncated"] is True
    assert result["results_total"] == 5
    assert len(result["results"]) == 3
    parsed = {"resources": {
        "aws_db_instance": {"ledger": {"publicly_accessible": True}},
        "aws_security_group": {"admin": {"ingress": [{
            "from_port": 22, "to_port": 22, "cidr_blocks": ["0.0.0.0/0"]
        }]}},
    }}
    findings = run_rules(parsed, "partial", scanner=result)
    assert any("ledger" in f.finding and "publicly accessible" in f.finding for f in findings)
    assert any("admin" in f.finding and "22" in f.finding for f in findings)
    assert any(f.type.value == "not-observable" and "truncat" in f.finding for f in findings)


def test_missing_binary_reports_unavailable(tmp_path):
    files = [_write(tmp_path / "main.tf", "")]

    result = scan.scan_files(
        str(tmp_path), files, trivy_path=str(tmp_path / "no-trivy")
    )

    assert result == {
        "status": "unavailable",
        "tool": "trivy",
        "reason": "scanner_not_installed",
    }


class _FakeS3:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def get_object(self, key: str) -> bytes:
        assert key == "uploads/r1.tar"
        return self.body


def _archive(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, text in files.items():
            data = text.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def test_handler_never_fails_the_review(monkeypatch):
    monkeypatch.setattr(
        scan, "scan_files", lambda *a, **k: (_ for _ in ()).throw(RuntimeError())
    )
    event = {
        "review_id": "r1",
        "archive_s3_key": "uploads/r1.tar",
        "report_bucket": "b",
    }

    result = scan.handler(event, None, s3_client=_FakeS3(_archive({"main.tf": ""})))

    assert result["status"] == "unavailable"
    assert result["reason"] == "RuntimeError"


def test_handler_reports_a_rejected_archive_as_unavailable():
    event = {
        "review_id": "r1",
        "archive_s3_key": "uploads/r1.tar",
        "report_bucket": "b",
    }

    result = scan.handler(
        event, None, s3_client=_FakeS3(_archive({"../escape.tf": ""}))
    )

    assert result == {
        "status": "unavailable",
        "tool": "trivy",
        "reason": "archive_rejected",
    }


def test_handler_cleans_up_its_work_directory(monkeypatch, tmp_path):
    created: list[str] = []
    real_mkdtemp = scan.tempfile.mkdtemp

    def tracking_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, dir=str(tmp_path), **kwargs)
        created.append(path)
        return path

    monkeypatch.setattr(scan.tempfile, "mkdtemp", tracking_mkdtemp)
    monkeypatch.setattr(
        scan, "scan_files", lambda *a, **k: {"status": "ok", "results": []}
    )
    event = {
        "review_id": "r1",
        "archive_s3_key": "uploads/r1.tar",
        "report_bucket": "b",
    }

    scan.handler(event, None, s3_client=_FakeS3(_archive({"main.tf": ""})))

    assert created and not any(os.path.exists(p) for p in created)


@pytest.mark.skipif(not os.environ.get("TRIVY_PATH"), reason="needs a Trivy binary")
def test_real_trivy_finds_a_trusted_check(tmp_path):
    files = [
        _write(
            tmp_path / "main.tf",
            'resource "aws_db_instance" "orders" {\n  publicly_accessible = true\n}\n',
        )
    ]

    result = scan.scan_files(str(tmp_path), files, os.environ["TRIVY_PATH"])

    assert result["status"] == "ok"
    assert any(r["check_id"] == "AWS-0180" for r in result["results"])
