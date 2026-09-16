"""Validate real S3 Vectors retrieval against the eval sets (ADR-0035/0036).

Run once after the corpus is embedded — embeds each eval query via Titan
V2, searches the real S3 Vectors index for the top-k nearest chunks, and
scores the results against the known-correct chunk_ids. Read-only against
the index (QueryVectors) plus a handful of embed calls — near zero cost,
safe to re-run anytime.

Scores EVAL_QUERIES (eval.py) and HOLDOUT_QUERIES (eval_holdout.py)
separately and reports Hit Rate@5 for each on its own — never merged into
one combined score, since keeping the dev set and the held-out set
separate is the entire point of having two sets.
"""

import os

from backend.corpus.eval import EvalQuery, score_retrieval
from backend.shared.clients import BedrockEmbeddingClient, S3VectorsClient

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
    for eval_query in queries:
        embedding = embedder.embed(eval_query.query)
        results = vectors_client.query_vectors(embedding, top_k=top_k)
        predictions[eval_query.query_id] = [result["key"] for result in results]
    return score_retrieval(predictions, queries=queries, k=top_k)


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


def main() -> None:
    from backend.corpus.eval import EVAL_QUERIES
    from backend.corpus.eval_holdout import HOLDOUT_QUERIES

    embedder = BedrockEmbeddingClient(region_name=_REGION)
    vectors_client = S3VectorsClient(
        bucket_name=_VECTOR_BUCKET_NAME, index_name=_VECTOR_INDEX_NAME, region_name=_REGION
    )

    print("=== Dev set (EVAL_QUERIES) ===")
    dev_result = run_validation(embedder, vectors_client, EVAL_QUERIES)
    print_report(dev_result)

    print("\n=== Held-out set (HOLDOUT_QUERIES) ===")
    holdout_result = run_validation(embedder, vectors_client, HOLDOUT_QUERIES)
    print_report(holdout_result)


if __name__ == "__main__":
    main()
