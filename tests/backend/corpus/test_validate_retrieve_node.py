import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from backend.corpus import validate_retrieve_node as runner
from backend.corpus.eval import EVAL_QUERIES
from backend.corpus.eval_holdout import HOLDOUT_QUERIES


def chunk():
    return {
        "chunk_id": EVAL_QUERIES[0].expected_chunk_ids[0],
        "document_id": "iam-best-practices",
        "source_url": "https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html",
        "source_edition": None,
        "retrieved_at": "2026-10-23T12:00:00Z",
        "heading_path": "IAM > Federation",
        "text": "Use federation for human users.",
        "content_hash": "a" * 64,
        "parser_version": "test-parser-v1",
        "corpus_version": "test-corpus-v1",
        "match_type": "vector",
    }


def test_plan_covers_complete_separate_sets_without_clients(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("plan constructed a client")

    monkeypatch.setattr(runner, "BedrockEmbeddingClient", forbidden)
    monkeypatch.setattr(runner, "S3VectorsClient", forbidden)
    monkeypatch.setattr("sys.argv", ["eval", "--plan"])
    assert runner.main() == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["case_ids"] == {
        "dev": [q.query_id for q in EVAL_QUERIES],
        "holdout": [q.query_id for q in HOLDOUT_QUERIES],
    }
    assert plan["partial"] is False
    assert plan["admission"]["planned_service_calls_upper_bound"] == 2 * (
        len(EVAL_QUERIES) + len(HOLDOUT_QUERIES)
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("retrieved_at", "invalid"),
        ("parser_version", ""),
        ("content_hash", "fake"),
        ("corpus_version", ""),
        ("document_id", ""),
    ],
)
def test_citation_metadata_contract_rejects_unusable_provenance(field, value):
    metadata = chunk()
    assert runner.citation_errors(metadata) == []
    metadata[field] = value
    assert runner.citation_errors(metadata)


def test_malformed_metadata_and_failed_query_do_not_erase_later_attempts(monkeypatch):
    monkeypatch.setattr(runner, "BedrockEmbeddingClient", lambda **kw: None)
    monkeypatch.setattr(runner, "S3VectorsClient", lambda **kw: None)
    monkeypatch.setattr(runner, "build_lexical_corpus_index_from_disk", dict)
    calls = []

    def retrieve(state):
        calls.append(state)
        if len(calls) == 1:
            raise RuntimeError("PRIVATE-CANARY")
        c = chunk()
        if len(calls) == 2:
            c["retrieved_at"] = "not-a-timestamp"
        return {"retrieved_chunks": [c]}

    monkeypatch.setattr(runner, "retrieve_node", retrieve)
    rows = runner.run(EVAL_QUERIES[:3])
    assert len(rows) == len(calls) == 3
    assert rows[0]["attempt_outcome"] == "failed"
    assert rows[1]["citation_errors"]
    assert rows[2]["citation_errors"] == []
    assert rows[2]["evidence_text_bytes"] == len(chunk()["text"].encode())
    assert rows[2]["merged_chunk_ids"] == [chunk()["chunk_id"]]
    assert "PRIVATE-CANARY" not in json.dumps(rows)
    summary = runner.summarize(rows)
    assert summary["scheduled"] == 3
    assert summary["returned"] == 2
    assert summary["passed"] is False


def test_missing_hits_fail_only_an_explicit_quality_threshold():
    row = {
        "attempt_outcome": "returned",
        "chunk_count": 1,
        "citation_errors": [],
        "expected_chunk_hit": False,
    }
    assert runner.summarize([row])["passed"] is True
    assert runner.summarize([row], 0.5)["passed"] is False
    assert runner.summarize([row], 0.5)["threshold_met"] is False
    assert runner.summarize([])["passed"] is False
    row["chunk_count"] = 0
    assert runner.summarize([row])["passed"] is False


def test_cli_contract_failure_returns_nonzero_and_keeps_separate_artifacts(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        runner,
        "admit_budget",
        lambda *a: SimpleNamespace(path="local-journal.json", summary=dict),
    )
    rows = []
    for q in (EVAL_QUERIES[0], HOLDOUT_QUERIES[0]):
        rows.append(
            {
                "query_id": q.query_id,
                "attempt_outcome": "returned",
                "expected_chunk_hit": True,
                "chunk_count": 1,
                "citation_errors": [],
            }
        )
    rows[1]["citation_errors"] = [{"errors": ["schema:retrieved_at"]}]
    monkeypatch.setattr(runner, "run", lambda *a: deepcopy(rows))
    monkeypatch.setattr(runner, "print_report", lambda *a: None)
    output = tmp_path / "results.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "eval",
            "--confirm-paid",
            "--limit",
            "1",
            "--max-paid-calls",
            "4",
            "--out",
            str(output),
        ],
    )
    assert runner.main() == 1
    artifact = json.loads(output.read_text())
    assert artifact["sets"]["dev"]["summary"]["passed"] is True
    assert artifact["sets"]["holdout"]["summary"]["passed"] is False
    assert artifact["sets"]["holdout"]["summary"]["semantic_support"] == "not_measured"
