import json
import re
from pathlib import Path

import pytest

from backend.corpus.eval import EVAL_QUERIES, score_retrieval

_CHUNKS_DIR = Path(__file__).parents[3] / "backend" / "corpus" / "data" / "chunks"

# One short, distinctive phrase per query that must appear (case-insensitive,
# whitespace-normalized) in at least one of its expected chunks' real text.
# This is a coarse guard against the exact failure mode found in the
# 2026-09 rechunks: a chunk_id staying "valid" (chunk still exists) while its
# content silently shifted to a different topic. It only catches gross
# drift, not fine-grained wrongness — see eval.py's module docstring for the
# manual verification this supplements.
_QUERY_KEYWORDS: dict[str, str] = {
    "q01": "federated",
    "q02": "temporary credentials",
    "q03": "MFA",
    "q04": "access keys",
    "q05": "root user",
    "q06": "origin failover",
    "q07": "decryption actions",
    "q08": "5.0.0",
    "q09": "Hardware MFA",
    "q10": "Security Reference Architecture",
    "q11": "most privileged user",
    "q12": "Infrastructure protection",
    "q13": "multi-account strategy",
    "q14": "external customer needs",
    "q15": "resiliency",
    "q16": "collocated data center",
    "q17": "Cloud Business",
    "q18": "sustainability of the cloud",
}


def test_eval_set_covers_every_ingested_source():
    covered = {q.expected_document_id for q in EVAL_QUERIES}
    assert covered == {
        "waf-operational-excellence-pillar",
        "waf-security-pillar",
        "waf-reliability-pillar",
        "waf-performance-efficiency-pillar",
        "waf-cost-optimization-pillar",
        "waf-sustainability-pillar",
        "aws-fsbp-standard",
        "aws-security-reference-architecture",
        "iam-best-practices",
        "aws-cis-foundations-mapping",
    }


def test_query_ids_are_unique():
    ids = [q.query_id for q in EVAL_QUERIES]
    assert len(ids) == len(set(ids))


@pytest.mark.skipif(
    not _CHUNKS_DIR.is_dir(), reason="corpus not ingested locally (backend/corpus/data/ is gitignored)"
)
def test_expected_chunk_ids_exist_in_the_real_ingested_corpus():
    real_ids_by_document: dict[str, set[str]] = {}
    for eval_query in EVAL_QUERIES:
        document_id = eval_query.expected_document_id
        if document_id not in real_ids_by_document:
            chunks = json.loads((_CHUNKS_DIR / f"{document_id}.json").read_text(encoding="utf-8"))
            real_ids_by_document[document_id] = {chunk["chunk_id"] for chunk in chunks}
        missing = set(eval_query.expected_chunk_ids) - real_ids_by_document[document_id]
        assert not missing, f"{eval_query.query_id}: {missing} not found in {document_id}.json"


def test_every_query_has_a_semantic_keyword():
    missing = [q.query_id for q in EVAL_QUERIES if q.query_id not in _QUERY_KEYWORDS]
    assert not missing, f"add a _QUERY_KEYWORDS entry for: {missing}"


@pytest.mark.skipif(
    not _CHUNKS_DIR.is_dir(), reason="corpus not ingested locally (backend/corpus/data/ is gitignored)"
)
def test_expected_chunks_actually_contain_their_query_keyword():
    real_ids_by_document: dict[str, dict[str, str]] = {}
    for eval_query in EVAL_QUERIES:
        document_id = eval_query.expected_document_id
        if document_id not in real_ids_by_document:
            chunks = json.loads((_CHUNKS_DIR / f"{document_id}.json").read_text(encoding="utf-8"))
            real_ids_by_document[document_id] = {chunk["chunk_id"]: chunk["text"] for chunk in chunks}
        texts_by_id = real_ids_by_document[document_id]
        keyword = _QUERY_KEYWORDS[eval_query.query_id].lower()
        found = any(
            keyword in re.sub(r"\s+", " ", texts_by_id.get(chunk_id, "")).lower()
            for chunk_id in eval_query.expected_chunk_ids
        )
        assert found, (
            f"{eval_query.query_id}: none of {eval_query.expected_chunk_ids} contain "
            f"keyword {_QUERY_KEYWORDS[eval_query.query_id]!r} — likely stale after a rechunk"
        )


def test_score_retrieval_counts_a_hit_when_any_expected_chunk_is_in_top_k():
    predictions = {"q01": ["some-other-chunk", "iam-best-practices-0003"]}
    result = score_retrieval(predictions, queries=EVAL_QUERIES[:1], k=5)
    assert result["hits"] == 1
    assert result["hit_rate_at_k"] == 1.0


def test_score_retrieval_misses_when_expected_chunk_is_outside_top_k():
    predictions = {"q01": ["a", "b", "iam-best-practices-0003"]}
    result = score_retrieval(predictions, queries=EVAL_QUERIES[:1], k=2)
    assert result["hits"] == 0
    assert result["hit_rate_at_k"] == 0.0


def test_score_retrieval_handles_a_query_with_no_predictions_at_all():
    result = score_retrieval({}, queries=EVAL_QUERIES[:1], k=5)
    assert result["hits"] == 0
    assert result["per_query"][0]["retrieved"] == []
