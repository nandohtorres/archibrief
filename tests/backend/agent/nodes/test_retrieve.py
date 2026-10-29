from backend.agent.nodes.retrieve import (
    COST_TOPIC_QUERIES,
    MAX_COST_TOPICS,
    MAX_TOPICS,
    TOPIC_QUERIES,
    TOPIC_TOP_K,
    RetrievedChunk,
    extract_lexical_terms,
    lexical_companion_lookup,
    merge_results,
    retrieve_node,
    topic_queries,
    vector_search,
)


def test_extract_lexical_terms_matches_waf_best_practice_ids():
    """Real WAF pillar ID formats carry digits before the hyphen ("SEC01",
    "COST01"), so a letters-only prefix pattern would miss all of them."""
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
    """Older corpus data written before content_type existed must not crash or
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
    """to_vector_record stores content_type in every vector's metadata,
    so vector_search must read it back out."""
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


class _RecordingClients:
    """Embedding and vector stubs that record each search."""

    def __init__(self) -> None:
        self.queries: list[str] = []
        self.top_ks: list[int] = []

    def embed(self, text: str) -> list[float]:
        self.queries.append(text)
        return [float(len(self.queries))]

    def query_vectors(self, query_vector: list[float], top_k: int) -> list[dict]:
        self.top_ks.append(top_k)
        n = int(query_vector[0])
        return [
            {
                "key": f"chunk-{n}-{i}",
                "distance": 0.1,
                "metadata": {"chunk_id": f"chunk-{n}-{i}"},
            }
            for i in range(top_k)
        ]


def _resources(*types: str) -> dict:
    return {"resources": [{"type": t, "name": "x", "settings": {}} for t in types]}


def test_topic_queries_follow_the_declared_resource_types_in_risk_order():
    queries = topic_queries(
        _resources("aws_sqs_queue", "aws_iam_role", "aws_s3_bucket")
    )
    assert queries == [TOPIC_QUERIES[0][1], TOPIC_QUERIES[7][1], COST_TOPIC_QUERIES[2][1]]
    assert topic_queries(None) == []
    assert topic_queries({"resources": "not a list"}) == []


def test_topic_queries_are_capped():
    every_type = [t for types, _ in TOPIC_QUERIES + COST_TOPIC_QUERIES for t in types]
    assert len(topic_queries(_resources(*every_type))) == MAX_TOPICS + MAX_COST_TOPICS


def test_cost_topics_are_searched_even_when_risk_topics_fill_their_cap():
    every_type = [t for types, _ in TOPIC_QUERIES for t in types]
    queries = topic_queries(_resources(*every_type, "aws_dynamodb_table"))
    assert queries[MAX_TOPICS:] == [COST_TOPIC_QUERIES[0][1], COST_TOPIC_QUERIES[1][1]]


def test_retrieve_adds_topic_searches_to_the_brief_search():
    clients = _RecordingClients()
    state = {
        "retrieval_query": "testyy",
        "embedding_client": clients,
        "vectors_client": clients,
        "terraform_resources": _resources(
            "aws_ecs_task_definition", "aws_cloudfront_distribution"
        ),
    }
    chunks = retrieve_node(state)["retrieved_chunks"]
    assert clients.queries[0] == "testyy"
    assert clients.queries[1:] == topic_queries(state["terraform_resources"])
    assert clients.top_ks == [8, TOPIC_TOP_K, TOPIC_TOP_K]
    # The brief's own results stay first.
    assert [c["chunk_id"] for c in chunks][:8] == [f"chunk-1-{i}" for i in range(8)]
    assert len(chunks) == 8 + 2 * TOPIC_TOP_K


def test_go_deeper_keeps_its_single_finding_scoped_search():
    clients = _RecordingClients()
    retrieve_node(
        {
            "retrieval_query": "finding-scoped query",
            "embedding_client": clients,
            "vectors_client": clients,
            "terraform_resources": _resources("aws_iam_role"),
            "deep_mode": True,
        }
    )
    assert clients.queries == ["finding-scoped query"]
