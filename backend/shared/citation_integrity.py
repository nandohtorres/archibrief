"""Offline reproducibility checks; quote membership is not semantic entailment."""

import hashlib
from datetime import datetime


def citation_errors(finding: dict, chunks: dict[str, dict]) -> list[str]:
    citation = finding.get("citation")
    if not citation:
        return (
            []
            if finding.get("type") in {"not-observable", "deterministic-rule-result"}
            else ["citation_missing"]
        )
    if not isinstance(citation, dict):
        return ["citation_invalid"]
    chunk = chunks.get(citation.get("chunk_id"))
    if not chunk:
        return ["chunk_missing"]
    errors = []
    text = chunk.get("text")
    if not isinstance(text, str):
        return ["chunk_text_invalid"]
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != chunk.get("content_hash"):
        errors.append("chunk_hash_mismatch")
    for field in ("content_hash", "source_url", "document_id", "parser_version", "corpus_version"):
        if not chunk.get(field) or citation.get(field) != chunk[field]:
            errors.append(f"citation_{field}_mismatch")
    for field in ("source_edition", "heading_path"):
        left, right = citation.get(field), chunk.get(field)
        if field == "heading_path":
            left = " > ".join(left) if isinstance(left, list) else left
            right = " > ".join(right) if isinstance(right, list) else right
        if left != right:
            errors.append(f"citation_{field}_mismatch")
    try:
        if datetime.fromisoformat(str(citation["retrieved_at"])) != datetime.fromisoformat(
            str(chunk["retrieved_at"])
        ):
            errors.append("citation_retrieved_at_mismatch")
    except (KeyError, ValueError):
        errors.append("citation_retrieved_at_invalid")
    quote = citation.get("exact_text_span")
    if not isinstance(quote, str) or not quote.strip() or quote not in text:
        errors.append("quote_not_exact_member")
    return errors
