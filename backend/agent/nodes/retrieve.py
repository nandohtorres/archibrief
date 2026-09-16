"""LangGraph node: Retrieve.

Runs inside the AgentCore Runtime + LangGraph subworkflow (ADR-0028), NOT
as a standalone Lambda.

Embeds query context via Titan V2 (working baseline candidate pending
evaluation, NOT a final/locked choice — ADR-0035), searches S3 Vectors,
returns top-k chunks with the full citation metadata set required by
ADR-0027/ADR-0036. Also does a deterministic/lexical companion lookup for
exact AWS identifiers/control names (ADR-0036), since vector recall alone
can miss them.

Actually calling Bedrock/S3 Vectors requires a live account (Deployment
Roadmap blocker) — that call is isolated in backend.shared.clients so this
node's retrieval/merge logic is real and independently testable against a
stubbed client.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.shared.clients import BedrockEmbeddingClient, S3VectorsClient

# The plain [A-Z]{2,}-\d+ branch never matched real AWS Well-Architected
# best-practice IDs like "SEC01-BP01" or "COST01-BP01" — those have
# digits between the letters and the hyphen on both sides, which the
# original pattern's letters-only-before-hyphen requirement excluded
# entirely. Found 2026-09-14 via Codex review of the first retrieval
# validation, confirmed by testing the pattern directly against every
# real WAF pillar ID prefix (SEC/COST/OPS/PERF/REL/SUS) — all failed to
# match before this fix.
AWS_IDENTIFIER_PATTERN = re.compile(
    r"\b(?:AWS::[A-Za-z0-9]+::[A-Za-z0-9]+|aws_[a-z0-9_]+"
    r"|[A-Z]{2,}\d{1,3}-[A-Z]{2,}\d{1,3}|[A-Z]{2,}-\d+(?:\.\d+)?)\b"
)


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    text: str
    source_url: str
    content_hash: str
    heading_path: str
    corpus_version: str
    score: float
    match_type: str  # "vector" | "lexical"
    # Citation-reproducibility fields (ADR-0027/ADR-0036) that used to be
    # dropped between the real Chunk model (backend/corpus/models.py) and
    # this retrieval-layer shape — reason_node needs all three to build a
    # real Citation without a second lookup. Found via Codex review of the
    # first real reason_node run, 2026-09-16.
    retrieved_at: str = ""
    source_edition: str | None = None
    parser_version: str = ""
    content_type: str = "prose"


def extract_lexical_terms(query: str) -> list[str]:
    return sorted(set(AWS_IDENTIFIER_PATTERN.findall(query)))


def lexical_companion_lookup(
    lexical_terms: list[str], corpus_index: dict[str, list[dict]]
) -> list[RetrievedChunk]:
    """corpus_index maps an exact identifier -> list of chunk metadata dicts.

    corpus_index is built at ingestion time from the curated knowledge
    base (Phase 2, not yet populated without a live account) — this
    function's contract is what that index must satisfy.
    """
    results: list[RetrievedChunk] = []
    for term in lexical_terms:
        for chunk in corpus_index.get(term, []):
            results.append(
                RetrievedChunk(
                    chunk_id=chunk["chunk_id"],
                    document_id=chunk["document_id"],
                    text=chunk["text"],
                    source_url=chunk["source_url"],
                    content_hash=chunk["content_hash"],
                    heading_path=chunk["heading_path"],
                    corpus_version=chunk["corpus_version"],
                    score=1.0,
                    match_type="lexical",
                    retrieved_at=chunk.get("retrieved_at", ""),
                    source_edition=chunk.get("source_edition"),
                    parser_version=chunk.get("parser_version", ""),
                    content_type=chunk.get("content_type", "prose"),
                )
            )
    return results


def vector_search(
    query_text: str,
    embedding_client: BedrockEmbeddingClient,
    vectors_client: S3VectorsClient,
    top_k: int = 8,
) -> list[RetrievedChunk]:
    query_vector = embedding_client.embed(query_text)
    matches = vectors_client.query_vectors(query_vector=query_vector, top_k=top_k)

    results = []
    for match in matches:
        metadata = match.get("metadata", {})
        # embed.py's to_vector_record() stores the raw chunk dict as metadata
        # verbatim, so heading_path arrives here as list[str] (Chunk's real
        # type), never the pre-joined string lexical_index.py produces for
        # the lexical path — join it the same way here so RetrievedChunk's
        # heading_path is consistently a str regardless of match_type. Bug
        # found via Codex review 2026-09-16: the old `metadata.get(...,  "")`
        # default silently accepted a list at runtime despite the dataclass
        # annotation claiming str.
        raw_heading_path = metadata.get("heading_path", [])
        heading_path = (
            " > ".join(raw_heading_path) if isinstance(raw_heading_path, list) else raw_heading_path
        )
        results.append(
            RetrievedChunk(
                chunk_id=metadata.get("chunk_id", match.get("key", "")),
                document_id=metadata.get("document_id", ""),
                text=metadata.get("text", ""),
                source_url=metadata.get("source_url", ""),
                content_hash=metadata.get("content_hash", ""),
                heading_path=heading_path,
                corpus_version=metadata.get("corpus_version", ""),
                score=match.get("distance", 0.0),
                match_type="vector",
                retrieved_at=metadata.get("retrieved_at", ""),
                source_edition=metadata.get("source_edition"),
                parser_version=metadata.get("parser_version", ""),
                content_type=metadata.get("content_type", "prose"),
            )
        )
    return results


def merge_results(
    vector_results: list[RetrievedChunk], lexical_results: list[RetrievedChunk]
) -> list[RetrievedChunk]:
    seen: set[str] = set()
    merged: list[RetrievedChunk] = []
    for chunk in [*lexical_results, *vector_results]:
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        merged.append(chunk)
    return merged


def retrieve_node(state: dict) -> dict:
    query_text = state["retrieval_query"]
    embedding_client: BedrockEmbeddingClient = state["embedding_client"]
    vectors_client: S3VectorsClient = state["vectors_client"]
    corpus_index: dict[str, list[dict]] = state.get("lexical_corpus_index", {})

    lexical_terms = extract_lexical_terms(query_text)
    lexical_results = lexical_companion_lookup(lexical_terms, corpus_index)
    vector_results = vector_search(query_text, embedding_client, vectors_client)
    merged = merge_results(vector_results, lexical_results)

    return {
        **state,
        "retrieved_chunks": [chunk.__dict__ for chunk in merged],
    }
