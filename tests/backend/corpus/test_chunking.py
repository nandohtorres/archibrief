from datetime import datetime, timezone

from backend.corpus.chunking import chunk_document, count_tokens
from backend.corpus.normalize import normalize_html

from .fixtures import build_sample_iam_doc_html


def _snapshot(long_paragraph_sentences: int = 200):
    return normalize_html(
        build_sample_iam_doc_html(long_paragraph_sentences),
        document_id="iam-best-practices",
        source_url="https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html",
        retrieved_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
        source_edition="2026-09-08",
    )


def test_table_code_and_list_each_become_their_own_untouched_chunk():
    chunks = chunk_document(_snapshot(), target_tokens=512)

    code_chunk = next(c for c in chunks if "create-analyzer" in c.text)
    list_chunk = next(c for c in chunks if c.text.startswith("- Enable Access Analyzer"))
    table_chunk = next(c for c in chunks if "AdministratorAccess" in c.text)

    assert code_chunk.heading_path[-1] == "Access Analyzer"
    assert list_chunk.heading_path[-1] == "Access Analyzer"
    assert table_chunk.heading_path[-1] == "Least privilege"


def test_table_code_and_list_chunks_carry_their_content_type():
    chunks = chunk_document(_snapshot(), target_tokens=512)

    code_chunk = next(c for c in chunks if "create-analyzer" in c.text)
    list_chunk = next(c for c in chunks if c.text.startswith("- Enable Access Analyzer"))
    table_chunk = next(c for c in chunks if "AdministratorAccess" in c.text)

    assert code_chunk.content_type == "code"
    assert list_chunk.content_type == "list"
    assert table_chunk.content_type == "table"


def test_grouped_prose_chunk_defaults_to_prose_content_type():
    chunks = chunk_document(_snapshot(), target_tokens=512)
    mfa_chunk = next(c for c in chunks if c.heading_path[-1] == "Multi-factor authentication")
    assert mfa_chunk.content_type == "prose"


def test_short_sections_produce_one_chunk_each():
    chunks = chunk_document(_snapshot(), target_tokens=512)
    mfa_chunks = [c for c in chunks if c.heading_path[-1] == "Multi-factor authentication"]
    assert len(mfa_chunks) == 1
    assert "Require MFA" in mfa_chunks[0].text


def test_oversized_section_falls_back_to_recursive_split_under_target():
    chunks = chunk_document(_snapshot(long_paragraph_sentences=200), target_tokens=512)
    long_chunks = [c for c in chunks if c.heading_path[-1] == "Long section"]

    assert len(long_chunks) > 1
    for chunk in long_chunks:
        assert count_tokens(chunk.text) <= 512 + 50  # small slack for sentence-boundary packing


def test_chunk_ids_are_sequential_and_unique():
    chunks = chunk_document(_snapshot(), target_tokens=512)
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))
    assert [c.sequence_index for c in chunks] == list(range(len(chunks)))


def test_chunk_carries_full_citation_metadata():
    chunks = chunk_document(_snapshot(), target_tokens=512, corpus_version="v3")
    chunk = chunks[0]
    assert chunk.document_id == "iam-best-practices"
    assert chunk.source_url.startswith("https://docs.aws.amazon.com")
    assert chunk.source_edition == "2026-09-08"
    assert chunk.corpus_version == "v3"
    assert chunk.license == "CC-BY-SA-4.0"
    assert chunk.parser_version
    assert chunk.chunker_version
    assert chunk.content_hash


def test_small_target_still_keeps_atomic_blocks_intact_even_if_over_budget():
    chunks = chunk_document(_snapshot(), target_tokens=5)
    code_chunk = next(c for c in chunks if "create-analyzer" in c.text)
    assert code_chunk.text == "aws accessanalyzer create-analyzer --analyzer-name example"
