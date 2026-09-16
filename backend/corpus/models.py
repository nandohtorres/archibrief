import hashlib
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel


class BlockKind(str, Enum):
    PARAGRAPH = "paragraph"
    TABLE = "table"
    CODE = "code"
    LIST = "list"


class Block(BaseModel):
    """One atomic content unit within a section. TABLE/CODE/LIST blocks are
    never split across chunks, per ADR-0036's "keep tables, warnings,
    ordered procedures, and code blocks intact where possible"."""

    kind: BlockKind
    text: str


class Section(BaseModel):
    """A heading-bounded region of a document, in document order."""

    heading_path: list[str]
    blocks: list[Block]


class DocumentSnapshot(BaseModel):
    """A versioned, normalized snapshot of one source document — the unit
    ADR-0036 requires before chunking ever happens."""

    document_id: str
    source_url: str
    retrieved_at: datetime
    source_edition: str | None
    license: str
    parser_version: str
    sections: list[Section]
    content_hash: str

    @staticmethod
    def compute_content_hash(sections: list[Section]) -> str:
        joined = "\x1f".join(
            "\x1e".join([*section.heading_path, *(block.text for block in section.blocks)])
            for section in sections
        )
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()


class Chunk(BaseModel):
    """One retrieval-eligible unit, carrying the full citation-reproducibility
    metadata ADR-0027/ADR-0036 require — every field here is what makes a
    generated finding's citation independently verifiable."""

    chunk_id: str
    document_id: str
    source_url: str
    source_edition: str | None
    license: str
    retrieved_at: datetime
    heading_path: list[str]
    text: str
    content_type: Literal["prose", "table", "list", "code"] = "prose"
    content_hash: str
    token_count: int
    sequence_index: int
    parser_version: str
    chunker_version: str
    corpus_version: str
