import hashlib
import re

from .models import BlockKind, Chunk, DocumentSnapshot, Section

# bumped 2026-09-15: no chunking-logic change of its own, but the BlockKind
# values it now receives from normalize_pdf's 3-finding follow-up
# segmentation fixes (colon-continuation, ordinal-vs-bullet list mixing,
# mangled-table LIST false-positive — see normalize_pdf.py's
# _PARSER_VERSION comment) change some block boundaries and content_type
# labels, so old chunks built under 1.1.0 are not equivalent to new ones
# under the same chunker_version.
_CHUNKER_VERSION = "1.2.0"
_ATOMIC_KINDS = {BlockKind.TABLE, BlockKind.CODE, BlockKind.LIST}
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_CONTENT_TYPE_BY_KIND = {
    BlockKind.PARAGRAPH: "prose",
    BlockKind.TABLE: "table",
    BlockKind.LIST: "list",
    BlockKind.CODE: "code",
}


def count_tokens(text: str) -> int:
    """Approximate token count (~1.3 tokens/word for English text) — no
    public Titan V2 tokenizer exists to count exactly; ADR-0035 already
    treats the embedding model as a baseline pending real evaluation, so
    this approximation is swapped for real measurement then, not now."""
    words = text.split()
    return max(1, round(len(words) * 1.3))


def chunk_document(
    snapshot: DocumentSnapshot,
    *,
    target_tokens: int = 512,
    corpus_version: str = "v1",
) -> list[Chunk]:
    """Structure-aware chunking per ADR-0036: split first on heading
    boundaries (one section below), keep table/code/list blocks intact as
    their own chunk, and only fall back to recursive text-splitting inside
    an oversized section/paragraph that has no clean structural boundary."""
    chunks: list[Chunk] = []
    for section in snapshot.sections:
        chunks.extend(_chunk_section(snapshot, section, target_tokens, corpus_version, len(chunks)))
    return chunks


def _chunk_section(
    snapshot: DocumentSnapshot,
    section: Section,
    target_tokens: int,
    corpus_version: str,
    start_index: int,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    group: list[str] = []
    group_tokens = 0
    group_kind: BlockKind | None = None

    def flush_group() -> None:
        nonlocal group, group_tokens, group_kind
        if group:
            chunks.append(
                _make_chunk(
                    snapshot,
                    section,
                    "\n\n".join(group),
                    corpus_version,
                    start_index + len(chunks),
                    _CONTENT_TYPE_BY_KIND[group_kind],
                )
            )
            group = []
            group_tokens = 0
            group_kind = None

    for block in section.blocks:
        block_tokens = count_tokens(block.text)

        if block.kind in _ATOMIC_KINDS:
            flush_group()
            chunks.append(
                _make_chunk(
                    snapshot,
                    section,
                    block.text,
                    corpus_version,
                    start_index + len(chunks),
                    _CONTENT_TYPE_BY_KIND[block.kind],
                )
            )
            continue

        if block_tokens > target_tokens:
            flush_group()
            for piece in _split_oversized_text(block.text, target_tokens):
                chunks.append(
                    _make_chunk(
                        snapshot,
                        section,
                        piece,
                        corpus_version,
                        start_index + len(chunks),
                        _CONTENT_TYPE_BY_KIND[block.kind],
                    )
                )
            continue

        if group and group_tokens + block_tokens > target_tokens:
            flush_group()

        group.append(block.text)
        group_tokens += block_tokens
        group_kind = block.kind

    flush_group()
    return chunks


def _split_oversized_text(text: str, target_tokens: int) -> list[str]:
    """Recursive fallback for a single block with no internal structure:
    pack whole sentences up to target_tokens, falling back to raw word
    slicing only if one sentence alone still exceeds it."""
    sentences = [s for s in _SENTENCE_SPLIT.split(text) if s]
    pieces: list[str] = []
    current: list[str] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current, current_tokens
        if current:
            pieces.append(" ".join(current))
            current = []
            current_tokens = 0

    for sentence in sentences:
        sentence_tokens = count_tokens(sentence)
        if sentence_tokens > target_tokens:
            flush()
            words = sentence.split()
            step = max(1, int(target_tokens / 1.3))
            for i in range(0, len(words), step):
                pieces.append(" ".join(words[i : i + step]))
            continue
        if current and current_tokens + sentence_tokens > target_tokens:
            flush()
        current.append(sentence)
        current_tokens += sentence_tokens

    flush()
    return pieces or [text]


def _make_chunk(
    snapshot: DocumentSnapshot,
    section: Section,
    text: str,
    corpus_version: str,
    sequence_index: int,
    content_type: str = "prose",
) -> Chunk:
    return Chunk(
        chunk_id=f"{snapshot.document_id}-{sequence_index:04d}",
        document_id=snapshot.document_id,
        source_url=snapshot.source_url,
        source_edition=snapshot.source_edition,
        license=snapshot.license,
        retrieved_at=snapshot.retrieved_at,
        heading_path=section.heading_path,
        text=text,
        content_type=content_type,
        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        token_count=count_tokens(text),
        sequence_index=sequence_index,
        parser_version=snapshot.parser_version,
        chunker_version=_CHUNKER_VERSION,
        corpus_version=corpus_version,
    )
