import json
import re
from pathlib import Path

import pytest

from backend.corpus.eval import EVAL_QUERIES, score_retrieval
from backend.corpus.eval_holdout import HOLDOUT_QUERIES

_CHUNKS_DIR = Path(__file__).parents[3] / "backend" / "corpus" / "data" / "chunks"

# See test_eval.py's _QUERY_KEYWORDS for what this guards against.
_QUERY_KEYWORDS: dict[str, str] = {
    "h01": "iterative phases",
    "h02": "at least one rule",
    "h03": "support role",
    "h04": "IAM Access Analyzer",
    "h05": "service control policies",
    "h06": "Use group and identity attributes",
    "h07": "hub-and-spoke",
    "h08": "emergency access",
    "h09": "escalate",
    "h10": "caching",
    "h11": "data retention policies",
    "h12": "backing up data",
    "h13": "degraded Availability Zone",
    "h14": "Consult regularly with experts",
}


def test_holdout_set_covers_every_ingested_source():
    covered = {q.expected_document_id for q in HOLDOUT_QUERIES}
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


def test_holdout_query_ids_are_unique():
    ids = [q.query_id for q in HOLDOUT_QUERIES]
    assert len(ids) == len(set(ids))


def test_holdout_query_ids_do_not_collide_with_the_dev_set():
    holdout_ids = {q.query_id for q in HOLDOUT_QUERIES}
    dev_ids = {q.query_id for q in EVAL_QUERIES}
    assert not (holdout_ids & dev_ids)


def test_holdout_set_does_not_reuse_expected_chunk_ids_from_the_dev_set():
    dev_chunk_ids: set[str] = set()
    for eval_query in EVAL_QUERIES:
        dev_chunk_ids.update(eval_query.expected_chunk_ids)

    for holdout_query in HOLDOUT_QUERIES:
        overlap = set(holdout_query.expected_chunk_ids) & dev_chunk_ids
        assert not overlap, f"{holdout_query.query_id} reuses dev-set chunk id(s) {overlap}"


@pytest.mark.skipif(
    not _CHUNKS_DIR.is_dir(), reason="corpus not ingested locally (backend/corpus/data/ is gitignored)"
)
def test_holdout_expected_chunk_ids_exist_in_the_real_ingested_corpus():
    real_ids_by_document: dict[str, set[str]] = {}
    for holdout_query in HOLDOUT_QUERIES:
        document_id = holdout_query.expected_document_id
        if document_id not in real_ids_by_document:
            chunks = json.loads((_CHUNKS_DIR / f"{document_id}.json").read_text(encoding="utf-8"))
            real_ids_by_document[document_id] = {chunk["chunk_id"] for chunk in chunks}
        missing = set(holdout_query.expected_chunk_ids) - real_ids_by_document[document_id]
        assert not missing, f"{holdout_query.query_id}: {missing} not found in {document_id}.json"


def test_every_holdout_query_has_a_semantic_keyword():
    missing = [q.query_id for q in HOLDOUT_QUERIES if q.query_id not in _QUERY_KEYWORDS]
    assert not missing, f"add a _QUERY_KEYWORDS entry for: {missing}"


@pytest.mark.skipif(
    not _CHUNKS_DIR.is_dir(), reason="corpus not ingested locally (backend/corpus/data/ is gitignored)"
)
def test_holdout_expected_chunks_actually_contain_their_query_keyword():
    real_ids_by_document: dict[str, dict[str, str]] = {}
    for holdout_query in HOLDOUT_QUERIES:
        document_id = holdout_query.expected_document_id
        if document_id not in real_ids_by_document:
            chunks = json.loads((_CHUNKS_DIR / f"{document_id}.json").read_text(encoding="utf-8"))
            real_ids_by_document[document_id] = {chunk["chunk_id"]: chunk["text"] for chunk in chunks}
        texts_by_id = real_ids_by_document[document_id]
        keyword = _QUERY_KEYWORDS[holdout_query.query_id].lower()
        found = any(
            keyword in re.sub(r"\s+", " ", texts_by_id.get(chunk_id, "")).lower()
            for chunk_id in holdout_query.expected_chunk_ids
        )
        assert found, (
            f"{holdout_query.query_id}: none of {holdout_query.expected_chunk_ids} contain "
            f"keyword {_QUERY_KEYWORDS[holdout_query.query_id]!r} — likely stale after a rechunk"
        )


def test_score_retrieval_works_against_the_holdout_set_via_the_queries_override():
    predictions = {"h04": ["some-other-chunk", "iam-best-practices-0014"]}
    result = score_retrieval(predictions, queries=HOLDOUT_QUERIES[:4], k=5)
    assert result["total_queries"] == 4
    assert result["hits"] == 1
