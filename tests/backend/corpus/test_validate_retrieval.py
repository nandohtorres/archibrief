import io
import json
from types import SimpleNamespace

from botocore.response import StreamingBody
from botocore.stub import Stubber

from backend.corpus.eval import EVAL_QUERIES, EvalQuery
from backend.corpus.validate_retrieval import run_validation
from backend.shared.clients import BedrockEmbeddingClient, S3VectorsClient


def test_failed_query_does_not_erase_later_queries_or_its_denominator():
    calls = []

    def embed(text):
        calls.append(text)
        if len(calls) == 1:
            raise RuntimeError("PRIVATE-CANARY")
        return [0.1]

    result = run_validation(
        SimpleNamespace(embed=embed),
        SimpleNamespace(query_vectors=lambda *args, **kw: []),
        EVAL_QUERIES[:2],
    )
    assert result["total_queries"] == len(result["attempts"]) == len(calls) == 2
    assert [row["attempt_outcome"] for row in result["attempts"]] == [
        "failed",
        "returned",
    ]
    assert "PRIVATE-CANARY" not in str(result["attempts"])


def _invoke_model_response(embedding: list[float]) -> dict:
    body = json.dumps({"embedding": embedding, "inputTextTokenCount": 5}).encode(
        "utf-8"
    )
    return {
        "body": StreamingBody(io.BytesIO(body), len(body)),
        "contentType": "application/json",
    }


def test_run_validation_scores_a_hit_when_retrieval_finds_the_expected_chunk():
    queries = [
        EvalQuery(
            query_id="q01",
            query="What does IAM say about federation?",
            expected_document_id="iam-best-practices",
            expected_chunk_ids=["iam-best-practices-0003"],
        )
    ]

    embedder = BedrockEmbeddingClient(region_name="us-east-1")
    embed_stubber = Stubber(embedder._client)
    embed_stubber.add_response("invoke_model", _invoke_model_response([0.1, 0.2]))
    embed_stubber.activate()

    vectors_client = S3VectorsClient(
        bucket_name="bkt", index_name="idx", region_name="us-east-1"
    )
    query_stubber = Stubber(vectors_client._client)
    query_stubber.add_response(
        "query_vectors",
        {
            "vectors": [
                {"key": "iam-best-practices-0003"},
                {"key": "some-other-chunk"},
            ],
            "distanceMetric": "cosine",
        },
        {
            "vectorBucketName": "bkt",
            "indexName": "idx",
            "queryVector": {"float32": [0.1, 0.2]},
            "topK": 5,
            "returnMetadata": True,
        },
    )
    query_stubber.activate()

    result = run_validation(embedder, vectors_client, queries, top_k=5)

    assert result["hits"] == 1
    assert result["hit_rate_at_k"] == 1.0
    embed_stubber.assert_no_pending_responses()
    query_stubber.assert_no_pending_responses()


def test_run_validation_scores_a_miss_when_expected_chunk_is_absent():
    queries = [
        EvalQuery(
            query_id="q01",
            query="What does IAM say about federation?",
            expected_document_id="iam-best-practices",
            expected_chunk_ids=["iam-best-practices-0003"],
        )
    ]

    embedder = BedrockEmbeddingClient(region_name="us-east-1")
    embed_stubber = Stubber(embedder._client)
    embed_stubber.add_response("invoke_model", _invoke_model_response([0.1, 0.2]))
    embed_stubber.activate()

    vectors_client = S3VectorsClient(
        bucket_name="bkt", index_name="idx", region_name="us-east-1"
    )
    query_stubber = Stubber(vectors_client._client)
    query_stubber.add_response(
        "query_vectors",
        {"vectors": [{"key": "unrelated-chunk"}], "distanceMetric": "cosine"},
        {
            "vectorBucketName": "bkt",
            "indexName": "idx",
            "queryVector": {"float32": [0.1, 0.2]},
            "topK": 5,
            "returnMetadata": True,
        },
    )
    query_stubber.activate()

    result = run_validation(embedder, vectors_client, queries, top_k=5)

    assert result["hits"] == 0
    assert result["hit_rate_at_k"] == 0.0
