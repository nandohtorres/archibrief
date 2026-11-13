"""The private evidence ledger is P0's authoritative scope record."""

import json
from copy import deepcopy

from backend.lambdas.finalize import handler as finalize
from tests.backend.p0_scope_fixtures import completed_scope


def _write(monkeypatch, extra):
    writes = []

    class Storage:
        def __init__(self, bucket):
            assert bucket == "reports"

        def put_object(self, key, body):
            writes.append((key, json.loads(body)))

    monkeypatch.setattr(finalize, "S3Client", Storage)
    event = {"review_id": "p0", "findings": [], "report_bucket": "reports", **extra}
    before = deepcopy(event)
    assert finalize.handler(event, None)["status"] == "complete"
    assert event == before
    assert len(writes) == 1
    assert writes[0][0] == "reports/p0/evidence-ledger.json"
    return writes[0][1]


def test_final_record_is_copied_exactly_into_authoritative_ledger(monkeypatch):
    record = completed_scope()
    ledger = _write(monkeypatch, {"review_scope": record})
    assert ledger["review_scope"] == record
    assert ledger["review_scope"]["status"] == "final"
    assert ledger["review_scope"]["declarations"][0]["parsed_key"] == "main"


def test_legacy_ledger_remains_without_scope_and_other_fields_are_unchanged(
    monkeypatch,
):
    legacy = _write(monkeypatch, {})
    assert "review_scope" not in legacy
    with_scope = _write(monkeypatch, {"review_scope": completed_scope()})
    assert with_scope.pop("review_scope") == completed_scope()
    legacy.pop("generated_at")
    with_scope.pop("generated_at")
    assert with_scope == legacy
