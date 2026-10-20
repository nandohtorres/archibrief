from backend.agent.nodes.retrieve import (
    RetrievedChunk,
    extract_lexical_terms,
    lexical_companion_lookup,
    merge_results,
    vector_search,
)


def test_extract_lexical_terms_matches_waf_best_practice_ids():
    """Regression test for the 2026-09-14 bug: these real WAF pillar ID
    formats all failed to match before the fix (letters-only-before-hyphen
    requirement excluded the digits in "SEC01", "COST01", etc.)."""
    query = "What does SEC01-BP01 say, and how does it relate to COST01-BP01, OPS01-BP01, and PERF01-BP01?"
    terms = extract_lexical_terms(query)
    assert terms == ["COST01-BP01", "OPS01-BP01", "PERF01-BP01", "SEC01-BP01"]


def test_extract_lexical_terms_still_matches_existing_formats():
    query = "Uses AWS::S3::Bucket and aws_s3_bucket, plus control IAM-123."
    terms = extract_lexical_terms(query)
    assert terms == ["AWS::S3::Bucket", "IAM-123", "aws_s3_bucket"]


def test_extract_lexical_terms_returns_empty_for_no_identifiers():
    assert extract_lexical_terms("What's the best way to secure an S3 bucket?") == []


def test_lexical_companion_lookup_returns_a_chunk_per_matching_term():
    corpus_index = {
        "SEC01-BP01": [
            {
                "chunk_id": "waf-security-pillar-0012",
                "document_id": "waf-security-pillar",
                "text": "Separate workloads using accounts.",
                "source_url": "https://example.com",
                "content_hash": "h1",
                "heading_path": "Security foundations > SEC01-BP01",
                "corpus_version": "v1",
                "content_type": "list",
            }
        ]
    }
    results = lexical_companion_lookup(["SEC01-BP01"], corpus_index)
    assert len(results) == 1
    assert results[0].chunk_id == "waf-security-pillar-0012"
    assert results[0].match_type == "lexical"
    assert results[0].score == 1.0
    assert results[0].content_type == "list"


def test_lexical_companion_lookup_defaults_content_type_to_prose_for_old_data():
    """Regression test for finding #6 (2026-09-15 Codex review): older
    corpus data written before content_type existed must not crash or
    silently surface as an empty/missing field downstream."""
    corpus_index = {
        "SEC01-BP01": [
            {
                "chunk_id": "waf-security-pillar-0012",
                "document_id": "waf-security-pillar",
                "text": "Separate workloads using accounts.",
                "source_url": "https://example.com",
                "content_hash": "h1",
                "heading_path": "Security foundations > SEC01-BP01",
                "corpus_version": "v1",
            }
        ]
    }
    results = lexical_companion_lookup(["SEC01-BP01"], corpus_index)
    assert results[0].content_type == "prose"


def test_lexical_companion_lookup_returns_empty_for_unmatched_terms():
    assert lexical_companion_lookup(["NOT-IN-INDEX"], {}) == []


def test_merge_results_deduplicates_and_prefers_lexical_over_vector():
    lexical = [
        RetrievedChunk(
            chunk_id="c-0001",
            document_id="d",
            text="lexical version",
            source_url="u",
            content_hash="h",
            heading_path="p",
            corpus_version="v1",
            score=1.0,
            match_type="lexical",
        )
    ]
    vector = [
        RetrievedChunk(
            chunk_id="c-0001",
            document_id="d",
            text="vector version",
            source_url="u",
            content_hash="h",
            heading_path="p",
            corpus_version="v1",
            score=0.8,
            match_type="vector",
        ),
        RetrievedChunk(
            chunk_id="c-0002",
            document_id="d",
            text="unique vector hit",
            source_url="u",
            content_hash="h",
            heading_path="p",
            corpus_version="v1",
            score=0.7,
            match_type="vector",
        ),
    ]
    merged = merge_results(vector, lexical)
    assert [c.chunk_id for c in merged] == ["c-0001", "c-0002"]
    assert merged[0].match_type == "lexical"


class _StubEmbeddingClient:
    def embed(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class _StubVectorsClient:
    def __init__(self, matches: list[dict]):
        self._matches = matches

    def query_vectors(self, *, query_vector, top_k):
        return self._matches


def test_vector_search_reads_content_type_from_metadata():
    """Regression test for finding #6 (2026-09-15 Codex review):
    to_vector_record already stores content_type in every vector's
    metadata, but vector_search wasn't reading it back out."""
    vectors_client = _StubVectorsClient(
        [
            {
                "key": "waf-security-pillar-0538",
                "distance": 0.12,
                "metadata": {
                    "chunk_id": "waf-security-pillar-0538",
                    "document_id": "waf-security-pillar",
                    "text": "| Role | Name |",
                    "source_url": "https://example.com",
                    "content_hash": "h1",
                    "heading_path": "Security foundations",
                    "corpus_version": "v3",
                    "content_type": "table",
                },
            }
        ]
    )
    results = vector_search(
        "incident contact table", _StubEmbeddingClient(), vectors_client
    )
    assert len(results) == 1
    assert results[0].content_type == "table"


def test_vector_search_defaults_content_type_to_prose_for_old_data():
    """Vectors written before content_type existed carry no such metadata
    key — must default to prose, not crash or surface None."""
    vectors_client = _StubVectorsClient(
        [
            {
                "key": "waf-security-pillar-0001",
                "distance": 0.2,
                "metadata": {
                    "chunk_id": "waf-security-pillar-0001",
                    "document_id": "waf-security-pillar",
                    "text": "Some prose.",
                    "source_url": "https://example.com",
                    "content_hash": "h1",
                    "heading_path": "Security foundations",
                    "corpus_version": "v1",
                },
            }
        ]
    )
    results = vector_search("query", _StubEmbeddingClient(), vectors_client)
    assert results[0].content_type == "prose"
