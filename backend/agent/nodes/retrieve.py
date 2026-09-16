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

AWS_IDENTIFIER_PATTERN = re.compile(
    r"\b(?:AWS::[A-Za-z0-9]+::[A-Za-z0-9]+|aws_[a-z0-9_]+|[A-Z]{2,}-\d+(?:\.\d+)?)\b"
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
        results.append(
            RetrievedChunk(
                chunk_id=metadata.get("chunk_id", match.get("key", "")),
                document_id=metadata.get("document_id", ""),
                text=metadata.get("text", ""),
                source_url=metadata.get("source_url", ""),
                content_hash=metadata.get("content_hash", ""),
                heading_path=metadata.get("heading_path", ""),
                corpus_version=metadata.get("corpus_version", ""),
                score=match.get("distance", 0.0),
                match_type="vector",
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
