from datetime import datetime, timezone

from backend.corpus.models import BlockKind
from backend.corpus.normalize import normalize_html

from .fixtures import build_sample_iam_doc_html


def _normalize(html: str | None = None):
    return normalize_html(
        html or build_sample_iam_doc_html(),
        document_id="iam-best-practices",
        source_url="https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html",
        retrieved_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
        source_edition="2026-09-08",
    )


def test_splits_on_heading_boundaries():
    snapshot = _normalize()
    heading_paths = [section.heading_path for section in snapshot.sections]
    assert heading_paths == [
        ["Security best practices in IAM"],
        ["Security best practices in IAM", "Multi-factor authentication"],
        ["Security best practices in IAM", "Least privilege"],
        ["Security best practices in IAM", "Least privilege", "Access Analyzer"],
        ["Security best practices in IAM", "Long section"],
    ]


def test_table_code_and_list_become_atomic_blocks():
    snapshot = _normalize()
    access_analyzer_section = next(
        s for s in snapshot.sections if s.heading_path[-1] == "Access Analyzer"
    )
    kinds = [block.kind for block in access_analyzer_section.blocks]
    assert kinds == [BlockKind.CODE, BlockKind.LIST]
    assert "create-analyzer" in access_analyzer_section.blocks[0].text
    assert access_analyzer_section.blocks[1].text.startswith("- Enable Access Analyzer")


def test_table_captured_under_its_own_heading_section():
    snapshot = _normalize()
    least_privilege_section = next(
        s for s in snapshot.sections if s.heading_path[-1] == "Least privilege"
    )
    kinds = [block.kind for block in least_privilege_section.blocks]
    assert BlockKind.TABLE in kinds
    table_block = next(b for b in least_privilege_section.blocks if b.kind == BlockKind.TABLE)
    assert "AdministratorAccess | Account" in table_block.text


def test_content_hash_is_deterministic_and_content_sensitive():
    a = _normalize()
    b = _normalize()
    assert a.content_hash == b.content_hash

    different = _normalize(build_sample_iam_doc_html(long_paragraph_sentences=201))
    assert different.content_hash != a.content_hash


def test_document_with_no_headings_forms_one_untitled_section():
    snapshot = _normalize("<html><body><p>No headings here.</p></body></html>")
    assert len(snapshot.sections) == 1
    assert snapshot.sections[0].heading_path == []
