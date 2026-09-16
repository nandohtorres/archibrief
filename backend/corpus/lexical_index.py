"""Build the lexical companion index (ADR-0036) from the real ingested corpus.

Offline/build-time helper, mirroring ingest.py/embed.py's "run locally,
read backend/corpus/data/chunks/" convention. Scans every real chunk for
exact AWS identifiers (SEC01-BP01, AWS::S3::Bucket, aws_s3_bucket, etc.)
using the SAME AWS_IDENTIFIER_PATTERN retrieve_node's lexical companion
lookup already defines, so the index this builds and the pattern that
later extracts identifiers from a query can never drift apart.

Not a Lambda, not run per-request — retrieve_node takes the resulting
{identifier: [chunk_metadata, ...]} dict as `state["lexical_corpus_index"]`
(see retrieve.py's lexical_companion_lookup docstring for the exact
contract), built once here and handed to it by whatever assembles the
real initial graph state.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.agent.nodes.retrieve import AWS_IDENTIFIER_PATTERN

_DATA_DIR = Path(__file__).parent / "data"
_CHUNKS_DIR = _DATA_DIR / "chunks"

# Only what lexical_companion_lookup actually reads off each chunk dict
# (see retrieve.py) — no reason to carry the rest of the raw chunk along.
_METADATA_KEYS = (
    "chunk_id",
    "document_id",
    "text",
    "source_url",
    "content_hash",
    "heading_path",
    "corpus_version",
    "content_type",
    "retrieved_at",
    "source_edition",
    "parser_version",
)


def _chunk_metadata(chunk: dict) -> dict:
    metadata = {key: chunk[key] for key in _METADATA_KEYS if key != "heading_path" and key != "content_type"}
    # heading_path is stored as a list of headings in the raw chunk data
    # (see backend/corpus/data/chunks/*.json); embed.py's embedding_input
    # joins it the same way when building what Titan actually sees, so
    # reuse that convention here for consistency.
    metadata["heading_path"] = " > ".join(chunk.get("heading_path") or [])
    metadata["content_type"] = chunk.get("content_type", "prose")
    return metadata


def _identifiers_in_chunk(chunk: dict) -> set[str]:
    heading_text = " ".join(chunk.get("heading_path") or [])
    found = set(AWS_IDENTIFIER_PATTERN.findall(heading_text))
    found |= set(AWS_IDENTIFIER_PATTERN.findall(chunk["text"]))
    return found


def build_lexical_corpus_index(chunks: list[dict]) -> dict[str, list[dict]]:
    """{identifier: [chunk_metadata, ...]} for every AWS_IDENTIFIER_PATTERN
    match found in a chunk's heading_path or text, across the whole corpus.
    A chunk can be indexed under more than one identifier; an identifier
    with multiple matching chunks keeps every one of them, in corpus scan
    order (sorted by document_id, then file order within each document)."""
    index: dict[str, list[dict]] = {}
    for chunk in chunks:
        for identifier in _identifiers_in_chunk(chunk):
            index.setdefault(identifier, []).append(_chunk_metadata(chunk))
    return index


def load_all_chunks() -> list[dict]:
    chunks: list[dict] = []
    for path in sorted(_CHUNKS_DIR.glob("*.json")):
        chunks.extend(json.loads(path.read_text(encoding="utf-8")))
    return chunks


def build_lexical_corpus_index_from_disk() -> dict[str, list[dict]]:
    return build_lexical_corpus_index(load_all_chunks())


def main() -> None:
    index = build_lexical_corpus_index_from_disk()
    total_chunk_refs = sum(len(v) for v in index.values())
    print(f"{len(index)} unique identifiers indexed, {total_chunk_refs} chunk references total.")
    for identifier in sorted(index)[:10]:
        chunk_ids = [c["chunk_id"] for c in index[identifier]]
        print(f"  {identifier} -> {chunk_ids}")


if __name__ == "__main__":
    main()
