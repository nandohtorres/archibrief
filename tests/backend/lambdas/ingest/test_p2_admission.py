import pytest

from backend.lambdas.ingest import handler as ingest
from tests.backend.lambdas.ingest.test_handler import _make_archive


@pytest.mark.parametrize("count", [51, 75, 100])
def test_oversize_stops_before_guardrail_client_creation_or_storage(tmp_path, monkeypatch, count):
    archive = tmp_path / "input.tar"
    source = "\n".join(f'resource "random_id" "r{n}" {{ count = 0 }}' for n in range(count))
    _make_archive(str(archive), {"main.tf": source.encode()})

    def forbidden(*args, **kwargs):
        pytest.fail("rejection must precede paid client resolution and parsed storage")

    monkeypatch.setattr(ingest, "_resolve_guardrails_client", forbidden)
    monkeypatch.setattr(ingest, "S3Client", forbidden)
    result = ingest.handler({
        "archive_path": str(archive), "workload_brief": "small workload",
        "review_id": "fixture", "report_bucket": "reports",
        "max_review_declarations": 10000,
    }, None)
    assert result == {
        "status": "rejected", "code": "resource_limit_exceeded",
        "scope_failure": {"known_y": count, "count_complete": True},
    }


def test_reused_local_module_counts_per_call_before_any_paid_work(tmp_path, monkeypatch):
    archive = tmp_path / "input.tar"
    _make_archive(str(archive), {
        "main.tf": b'module "a" { source = "./unit" }\nmodule "b" { source = "./unit" }',
        "unit/main.tf": "\n".join(f'resource "aws_s3_bucket" "r{n}" {{}}' for n in range(26)).encode(),
    })
    monkeypatch.setattr(ingest, "_resolve_guardrails_client", lambda *args: pytest.fail("paid client"))
    result = ingest.handler({"archive_path": str(archive), "workload_brief": "test"}, None)
    assert result["scope_failure"]["known_y"] == 52
    assert result["code"] == "resource_limit_exceeded"
