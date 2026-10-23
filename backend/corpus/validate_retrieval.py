"""Validate real S3 Vectors retrieval against the eval sets (ADR-0035/0036).

Run once after the corpus is embedded — embeds each eval query via Titan
V2, searches the real S3 Vectors index for the top-k nearest chunks, and
scores the results against the known-correct chunk_ids. Read-only against
the index (QueryVectors), with paid embedding/query calls. CLI execution requires
confirmation and an explicit service-call limit; previews make no AWS calls.

Scores EVAL_QUERIES (eval.py) and HOLDOUT_QUERIES (eval_holdout.py)
separately and reports Hit Rate@5 for each on its own — never merged into
one combined score, since keeping the dev set and the held-out set
separate is the entire point of having two sets.
"""

import argparse
import json
import os

from backend.corpus.eval import EvalQuery, score_retrieval
from backend.shared.clients import BedrockEmbeddingClient, S3VectorsClient
from backend.shared.evaluation_budget import (
    EvaluationLimitReached,
    add_budget_options,
    admit_budget,
    budget_plan,
)

_VECTOR_BUCKET_NAME = os.environ.get("ARCHIBRIEF_VECTOR_BUCKET", "archibrief-dev-kb")
_VECTOR_INDEX_NAME = os.environ.get("ARCHIBRIEF_VECTOR_INDEX", "archibrief-dev-kb-index")
_REGION = os.environ.get("AWS_REGION", "us-east-1")
_TOP_K = 5


def run_validation(
    embedder: BedrockEmbeddingClient,
    vectors_client: S3VectorsClient,
    queries: list[EvalQuery],
    top_k: int = _TOP_K,
) -> dict:
    predictions: dict[str, list[str]] = {}
    attempts = []
    for eval_query in queries:
        try:
            embedding = embedder.embed(eval_query.query)
            results = vectors_client.query_vectors(embedding, top_k=top_k)
            predictions[eval_query.query_id] = [result["key"] for result in results]
            attempts.append({"query_id": eval_query.query_id, "attempt_outcome": "returned"})
        except Exception as exc:  # noqa: BLE001 - keep failed cases in the denominator
            predictions[eval_query.query_id] = []
            attempts.append(
                {
                    "query_id": eval_query.query_id,
                    "attempt_outcome": "not_run"
                    if isinstance(exc, EvaluationLimitReached)
                    else "failed",
                    "error_kind": type(exc).__name__,
                }
            )
    return {**score_retrieval(predictions, queries=queries, k=top_k), "attempts": attempts}


def print_report(result: dict) -> None:
    print(
        f"Hit Rate@{result['k']}: {result['hit_rate_at_k']:.0%} "
        f"({result['hits']}/{result['total_queries']})\n"
    )
    for per_query in result["per_query"]:
        status = "OK  " if per_query["hit"] else "MISS"
        print(f"{status} {per_query['query_id']}")
        print(f"     expected:  {per_query['expected']}")
        print(f"     retrieved: {per_query['retrieved']}")
    print(json.dumps({"attempts": result["attempts"]}))


def main() -> int:
    from backend.corpus.eval import EVAL_QUERIES
    from backend.corpus.eval_holdout import HOLDOUT_QUERIES

    parser = argparse.ArgumentParser(description="Paid vector-only retrieval diagnostic")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--confirm-paid", action="store_true")
    parser.add_argument("--limit", type=int)
    add_budget_options(parser)
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    dev, holdout = EVAL_QUERIES[: args.limit], HOLDOUT_QUERIES[: args.limit]
    calls = 2 * (len(dev) + len(holdout))
    plan = {
        "partial": args.limit is not None,
        "case_ids": {"dev": [q.query_id for q in dev], "holdout": [q.query_id for q in holdout]},
        "admission": budget_plan(args, parser, calls),
    }
    if args.plan:
        print(json.dumps(plan, indent=2))
        return 0
    if not args.confirm_paid:
        parser.error("paid AWS validation requires --confirm-paid")
    budget = admit_budget(args, parser, calls)
    embedder = budget.wrap(
        BedrockEmbeddingClient(region_name=_REGION, no_retries=True, read_timeout_seconds=30),
        "embedding",
    )
    vectors_client = budget.wrap(
        S3VectorsClient(
            bucket_name=_VECTOR_BUCKET_NAME,
            index_name=_VECTOR_INDEX_NAME,
            region_name=_REGION,
            no_retries=True,
            read_timeout_seconds=30,
        ),
        "vectors",
    )

    print("=== Dev set (EVAL_QUERIES) ===")
    dev_result = run_validation(embedder, vectors_client, dev)
    print_report(dev_result)

    print("\n=== Held-out set (HOLDOUT_QUERIES) ===")
    holdout_result = run_validation(embedder, vectors_client, holdout)
    print_report(holdout_result)
    print(json.dumps({"call_journal": str(budget.path), "admission": budget.summary()}, indent=2))
    return (
        1
        if any(
            a["attempt_outcome"] != "returned"
            for a in [*dev_result["attempts"], *holdout_result["attempts"]]
        )
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
