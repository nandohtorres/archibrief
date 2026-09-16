"""Shared AWS client adapters (Bedrock, DynamoDB, S3, S3 Vectors).

Thin wrappers around boto3 so call sites depend on a narrow interface
instead of raw boto3 clients — makes unit tests swap in a stub/mock
without patching boto3 globally, and gives each AWS surface one place to
add retry/error handling later.

None of these can be exercised against real AWS until account/IAM
bootstrap (see Work-Project-Deployment-Roadmap.md) — that's an account
problem, not a code problem, so the adapters are implemented for real and
tested against botocore.stub.Stubber / moto.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import boto3


@dataclass
class DynamoDBClient:
    table_name: str
    region_name: str = "us-east-1"

    def __post_init__(self) -> None:
        self._resource = boto3.resource("dynamodb", region_name=self.region_name)
        self._table = self._resource.Table(self.table_name)

    def put_item(self, item: dict[str, Any]) -> None:
        self._table.put_item(Item=item)

    def get_item(self, key: dict[str, Any]) -> dict[str, Any] | None:
        response = self._table.get_item(Key=key)
        return response.get("Item")

    def query(self, **kwargs: Any) -> list[dict[str, Any]]:
        response = self._table.query(**kwargs)
        return response.get("Items", [])


@dataclass
class S3Client:
    bucket: str
    region_name: str = "us-east-1"

    def __post_init__(self) -> None:
        self._client = boto3.client("s3", region_name=self.region_name)

    def put_object(self, key: str, body: bytes, content_type: str = "application/json") -> None:
        self._client.put_object(Bucket=self.bucket, Key=key, Body=body, ContentType=content_type)

    def get_object(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()


@dataclass
class S3VectorsClient:
    """Wraps AWS S3 Vectors (ADR-0007) — a rebuildable index, not source of truth."""

    bucket_name: str
    index_name: str
    region_name: str = "us-east-1"

    def __post_init__(self) -> None:
        self._client = boto3.client("s3vectors", region_name=self.region_name)

    def put_vectors(self, vectors: list[dict[str, Any]]) -> None:
        self._client.put_vectors(
            vectorBucketName=self.bucket_name,
            indexName=self.index_name,
            vectors=vectors,
        )

    def query_vectors(
        self, query_vector: list[float], top_k: int, metadata_filter: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        kwargs: dict[str, Any] = {
            "vectorBucketName": self.bucket_name,
            "indexName": self.index_name,
            "queryVector": {"float32": query_vector},
            "topK": top_k,
            "returnMetadata": True,
        }
        if metadata_filter:
            kwargs["filter"] = metadata_filter
        response = self._client.query_vectors(**kwargs)
        return response.get("vectors", [])


@dataclass
class BedrockEmbeddingClient:
    """Titan V2 embeddings — baseline candidate, not a locked final choice (ADR-0035)."""

    model_id: str = "amazon.titan-embed-text-v2:0"
    region_name: str = "us-east-1"

    def __post_init__(self) -> None:
        self._client = boto3.client("bedrock-runtime", region_name=self.region_name)

    def embed(self, text: str) -> list[float]:
        response = self._client.invoke_model(
            modelId=self.model_id,
            body=json.dumps({"inputText": text}),
        )
        payload = json.loads(response["body"].read())
        return payload["embedding"]


@dataclass
class BedrockReasoningClient:
    """Claude via Bedrock — the core reasoning/synthesis engine (ADR-0006)."""

    model_id: str
    region_name: str = "us-east-1"

    def __post_init__(self) -> None:
        self._client = boto3.client("bedrock-runtime", region_name=self.region_name)

    def converse(self, system_prompt: str, user_content: str, max_tokens: int) -> str:
        response = self._client.converse(
            modelId=self.model_id,
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": [{"text": user_content}]}],
            inferenceConfig={"maxTokens": max_tokens},
        )
        return response["output"]["message"]["content"][0]["text"]


@dataclass
class GuardrailsClient:
    """Bedrock Guardrails prompt-attack classifier (ADR-0033) — production path.

    Does not inspect tool/retrieval results (ADR-0038); only text passed to
    apply_guardrail. Callers must also apply provenance checks on retrieved
    evidence.
    """

    guardrail_id: str
    guardrail_version: str
    region_name: str = "us-east-1"

    def __post_init__(self) -> None:
        self._client = boto3.client("bedrock-runtime", region_name=self.region_name)

    def check(self, text: str, source: str = "INPUT") -> bool:
        response = self._client.apply_guardrail(
            guardrailIdentifier=self.guardrail_id,
            guardrailVersion=self.guardrail_version,
            source=source,
            content=[{"text": {"text": text}}],
        )
        return response["action"] == "NONE"
