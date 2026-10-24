"""Validate retrieve_node end-to-end against the real live index (ADR-0036).

Sibling to validate_retrieval.py, but exercises the actual LangGraph node
(retrieve_node) rather than calling vector search directly — confirms the
merged vector+lexical retrieval path, the full citation metadata shape,
and the lexical companion index built by lexical_index.py all work
together against real Titan embed calls and a real S3 Vectors query.
Read-only against the index, with paid embedding/query calls. CLI execution
requires confirmation and an explicit service-call limit, like validate_retrieval.py.

Not a pytest test — run directly, matching validate_retrieval.py's own
convention (this repo's tests/ tree only exercises node logic against
stubbed clients; hitting real AWS happens through these standalone
scripts instead of pytest's skipif-on-missing-local-data pattern, since
the CLI gate is explicit paid admission, not merely available credentials).
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from pydantic import ValidationError

from backend.agent.nodes.retrieve import extract_lexical_terms, retrieve_node
from backend.corpus.eval import EVAL_QUERIES, EvalQuery
from backend.corpus.eval_holdout import HOLDOUT_QUERIES
from backend.corpus.lexical_index import build_lexical_corpus_index_from_disk
from backend.shared.clients import BedrockEmbeddingClient, S3VectorsClient
from backend.shared.evaluation_budget import (
    EvaluationBudget,
    EvaluationLimitReached,
    add_budget_options,
    admit_budget,
    budget_plan,
)
from backend.shared.evaluation_manifest import attach_manifest, evidence_manifest
from backend.shared.models.finding import Citation

_VECTOR_BUCKET_NAME = os.environ.get("ARCHIBRIEF_VECTOR_BUCKET", "archibrief-dev-kb")
_VECTOR_INDEX_NAME = os.environ.get("ARCHIBRIEF_VECTOR_INDEX", "archibrief-dev-kb-index")
_REGION = os.environ.get("AWS_REGION", "us-east-1")

_REQUIRED_CITATION_FIELDS = (
    "chunk_id",
    "source_url",
    "content_hash",
    "heading_path",
    "corpus_version",
    "document_id",
    "retrieved_at",
    "parser_version",
    "text",
)

# A handful of EVAL_QUERIES queries reused as-is (ADR-0035/0036's frozen,
# already-verified query set) rather than inventing new ones. q13 contains
# a real WAF best-practice identifier (SEC01-BP01) so it's the one that
# must exercise the lexical companion path, not just vector search.
_SAMPLE_QUERY_IDS = ["q01", "q06", "q09", "q13", "q17"]


def _sample_queries() -> list[EvalQuery]:
    by_id = {q.query_id: q for q in EVAL_QUERIES}
    return [by_id[query_id] for query_id in _SAMPLE_QUERY_IDS]


def citation_errors(chunk: dict) -> list[str]:
    """Exercise the downstream schema, then explicit provenance requirements.

    The hash identifies the document snapshot, not just this chunk's text.
    Checking its shape does not verify it against a downloaded source.
    """
    errors = [f"missing:{field}" for field in _REQUIRED_CITATION_FIELDS if not chunk.get(field)]
    try:
        Citation.model_validate(
            {
                **chunk,
                "source_edition": chunk.get("source_edition"),
                "exact_text_span": chunk.get("text"),
            }
        )
    except ValidationError as exc:
        errors.extend("schema:" + ".".join(map(str, error["loc"])) for error in exc.errors())
    if not re.fullmatch(r"[0-9a-f]{64}", str(chunk.get("content_hash", ""))):
        errors.append("invalid:content_hash")
    return sorted(set(errors))


def summarize(reports: list[dict], min_hit_rate: float | None = None) -> dict:
    returned = [row for row in reports if row["attempt_outcome"] == "returned"]
    hits = sum(bool(row.get("expected_chunk_hit")) for row in reports)
    rate = hits / len(reports) if reports else 0.0
    metadata_valid = bool(returned) and all(
        row.get("chunk_count", 0) > 0 and not row.get("citation_errors") for row in returned
    )
    complete = len(returned) == len(reports) and bool(reports)
    threshold_met = rate >= min_hit_rate if min_hit_rate is not None else None
    return {
        "scheduled": len(reports),
        "returned": len(returned),
        "hits": hits,
        "hit_rate_all_attempts": rate,
        "metadata_valid": metadata_valid,
        "min_hit_rate": min_hit_rate,
        "threshold_met": threshold_met,
        "passed": complete and metadata_valid and threshold_met is not False,
        "semantic_support": "not_measured",
        "source_hash_verification": "not_measured",
    }


def run(queries: list[EvalQuery], budget: EvaluationBudget | None = None) -> list[dict]:
    embedding_client = BedrockEmbeddingClient(
        region_name=_REGION, no_retries=True, read_timeout_seconds=30
    )
    vectors_client = S3VectorsClient(
        bucket_name=_VECTOR_BUCKET_NAME,
        index_name=_VECTOR_INDEX_NAME,
        region_name=_REGION,
        no_retries=True,
        read_timeout_seconds=30,
    )
    if budget:
        embedding_client = budget.wrap(embedding_client, "embedding")
        vectors_client = budget.wrap(vectors_client, "vectors")
    lexical_corpus_index = build_lexical_corpus_index_from_disk()

    reports = []
    for eval_query in queries:
        state = {
            "retrieval_query": eval_query.query,
            "embedding_client": embedding_client,
            "vectors_client": vectors_client,
            "lexical_corpus_index": lexical_corpus_index,
        }
        try:
            result = retrieve_node(state)
        except Exception as exc:  # noqa: BLE001 - never erase later scheduled queries
            reports.append(
                {
                    "query_id": eval_query.query_id,
                    "query": eval_query.query,
                    "attempt_outcome": "not_run"
                    if isinstance(exc, EvaluationLimitReached)
                    else "failed",
                    "error_kind": type(exc).__name__,
                }
            )
            continue
        chunks = result["retrieved_chunks"]
        lexical_terms = extract_lexical_terms(eval_query.query)
        lexical_hits = [c for c in chunks if c["match_type"] == "lexical"]
        missing_fields = [
            field for chunk in chunks for field in _REQUIRED_CITATION_FIELDS if not chunk.get(field)
        ]
        errors = [
            {"chunk_index": index, "errors": found}
            for index, chunk in enumerate(chunks)
            if (found := citation_errors(chunk))
        ]
        reports.append(
            {
                "query_id": eval_query.query_id,
                "attempt_outcome": "returned",
                "query": eval_query.query,
                "lexical_terms": lexical_terms,
                "chunk_count": len(chunks),
                "lexical_hit_count": len(lexical_hits),
                "expected_chunk_hit": any(
                    c["chunk_id"] in eval_query.expected_chunk_ids for c in chunks
                ),
                "missing_citation_fields": missing_fields,
                "citation_errors": errors,
                "merged_chunk_ids": [c["chunk_id"] for c in chunks],
                "merged_match_types": [c["match_type"] for c in chunks],
                "retrieved_evidence": evidence_manifest(chunks),
                "evidence_text_bytes": sum(len(c["text"].encode("utf-8")) for c in chunks),
                "sample_chunk_ids": [c["chunk_id"] for c in chunks[:5]],
            }
        )
    return reports


def print_report(reports: list[dict]) -> None:
    for report in reports:
        print(f"{report['query_id']}: {report['query']}")
        if report["attempt_outcome"] != "returned":
            print(f"  {report['attempt_outcome']}: {report['error_kind']}")
            continue
        print(f"  lexical_terms:      {report['lexical_terms']}")
        print(
            f"  chunks retrieved:   {report['chunk_count']} (lexical hits: {report['lexical_hit_count']})"
        )
        print(f"  expected chunk hit: {report['expected_chunk_hit']}")
        print(f"  missing citations:  {report['missing_citation_fields'] or 'none'}")
        print(f"  citation contract:  {report['citation_errors'] or 'valid'}")
        print(f"  sample chunk_ids:   {report['sample_chunk_ids']}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Paid merged-retrieval diagnostic")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--confirm-paid", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--sample", action="store_true", help="legacy five-query diagnostic only")
    parser.add_argument(
        "--min-hit-rate", type=float, help="explicit per-set all-attempt threshold (0..1)"
    )
    parser.add_argument("--out", type=Path, help="structured diagnostic artifact")
    add_budget_options(parser)
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    if args.min_hit_rate is not None and not 0 <= args.min_hit_rate <= 1:
        parser.error("--min-hit-rate must be between 0 and 1")
    selected = (
        {"sample": _sample_queries()}
        if args.sample
        else {"dev": EVAL_QUERIES, "holdout": HOLDOUT_QUERIES}
    )
    selected = {name: cases[: args.limit] for name, cases in selected.items()}
    queries = [query for cases in selected.values() for query in cases]
    calls = 2 * len(queries)
    attach_manifest(
        args,
        {
            name: [query.model_dump(mode="json") for query in cases]
            for name, cases in selected.items()
        },
        {
            "region": _REGION,
            "vector_bucket": _VECTOR_BUCKET_NAME,
            "vector_index": _VECTOR_INDEX_NAME,
            "vector_top_k": 8,
            "merge": "lexical-first-deduplicate-by-chunk-id",
        },
    )
    plan = {
        "partial": args.limit is not None or args.sample,
        "case_ids": {name: [q.query_id for q in cases] for name, cases in selected.items()},
        "mode": "controlled-merged-retrieval-component",
        "min_hit_rate": args.min_hit_rate,
        "admission": budget_plan(args, parser, calls),
    }
    if args.plan:
        print(json.dumps(plan, indent=2))
        return 0
    if not args.confirm_paid:
        parser.error("paid AWS validation requires --confirm-paid")
    budget = admit_budget(args, parser, calls)
    reports = run(queries, budget)
    print_report(reports)
    sets = {}
    for name, cases in selected.items():
        ids = {query.query_id for query in cases}
        rows = [row for row in reports if row["query_id"] in ids]
        sets[name] = {"summary": summarize(rows, args.min_hit_rate), "attempts": rows}
    artifact = {
        "metadata": plan,
        "sets": sets,
        "call_journal": str(budget.path),
        "admission": budget.summary(),
    }
    if args.out:
        args.out.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(json.dumps(artifact, indent=2))
    return 0 if all(result["summary"]["passed"] for result in sets.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
