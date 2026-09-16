from backend.corpus.lexical_index import build_lexical_corpus_index


def test_build_lexical_corpus_index_indexes_a_heading_identifier():
    chunks = [
        {
            "chunk_id": "waf-security-pillar-0031",
            "document_id": "waf-security-pillar",
            "text": "Separate workloads using multiple accounts.",
            "source_url": "https://example.com",
            "content_hash": "h1",
            "heading_path": ["Security foundations", "SEC01-BP01"],
            "corpus_version": "v3",
            "content_type": "prose",
        }
    ]
    index = build_lexical_corpus_index(chunks)
    assert list(index) == ["SEC01-BP01"]
    assert index["SEC01-BP01"][0]["chunk_id"] == "waf-security-pillar-0031"
    assert index["SEC01-BP01"][0]["heading_path"] == "Security foundations > SEC01-BP01"


def test_build_lexical_corpus_index_matches_identifiers_in_body_text_too():
    chunks = [
        {
            "chunk_id": "aws-fsbp-standard-0008",
            "document_id": "aws-fsbp-standard",
            "text": "KMS-15 restricts customer managed policies from allowing decrypt actions.",
            "source_url": "https://example.com",
            "content_hash": "h2",
            "heading_path": [],
            "corpus_version": "v3",
            "content_type": "prose",
        }
    ]
    index = build_lexical_corpus_index(chunks)
    assert list(index) == ["KMS-15"]


def test_build_lexical_corpus_index_indexes_a_chunk_under_every_identifier_it_matches():
    chunks = [
        {
            "chunk_id": "waf-cost-optimization-pillar-0000",
            "document_id": "waf-cost-optimization-pillar",
            "text": "See COST01-BP01 and COST01-BP02 for detail.",
            "source_url": "https://example.com",
            "content_hash": "h3",
            "heading_path": [],
            "corpus_version": "v3",
            "content_type": "prose",
        }
    ]
    index = build_lexical_corpus_index(chunks)
    assert set(index) == {"COST01-BP01", "COST01-BP02"}
    assert index["COST01-BP01"][0]["chunk_id"] == "waf-cost-optimization-pillar-0000"
    assert index["COST01-BP02"][0]["chunk_id"] == "waf-cost-optimization-pillar-0000"


def test_build_lexical_corpus_index_defaults_content_type_to_prose_for_old_data():
    chunks = [
        {
            "chunk_id": "waf-security-pillar-0031",
            "document_id": "waf-security-pillar",
            "text": "SEC01-BP01 guidance.",
            "source_url": "https://example.com",
            "content_hash": "h1",
            "heading_path": [],
            "corpus_version": "v3",
        }
    ]
    index = build_lexical_corpus_index(chunks)
    assert index["SEC01-BP01"][0]["content_type"] == "prose"


def test_build_lexical_corpus_index_returns_empty_for_no_identifiers():
    chunks = [
        {
            "chunk_id": "iam-best-practices-0001",
            "document_id": "iam-best-practices",
            "text": "Use temporary credentials wherever possible.",
            "source_url": "https://example.com",
            "content_hash": "h1",
            "heading_path": [],
            "corpus_version": "v3",
            "content_type": "prose",
        }
    ]
    assert build_lexical_corpus_index(chunks) == {}
