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

    def list_vectors(self, return_metadata: bool = True) -> list[dict[str, Any]]:
        vectors: list[dict[str, Any]] = []
        next_token: str | None = None
        while True:
            kwargs: dict[str, Any] = {
                "vectorBucketName": self.bucket_name,
                "indexName": self.index_name,
                "returnMetadata": return_metadata,
            }
            if next_token:
                kwargs["nextToken"] = next_token
            response = self._client.list_vectors(**kwargs)
            vectors.extend(response.get("vectors", []))
            next_token = response.get("nextToken")
            if not next_token:
                break
        return vectors

    def delete_vectors(self, keys: list[str]) -> None:
        self._client.delete_vectors(
            vectorBucketName=self.bucket_name,
            indexName=self.index_name,
            keys=keys,
        )


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


class ModelOutputTruncated(Exception):
    """Raised when Bedrock reports stopReason == "max_tokens" — the response
    was cut off mid-generation, so anything parsed from it (JSON, a tool
    call) may be silently incomplete rather than absent."""

    def __init__(self, stop_reason: str) -> None:
        self.stop_reason = stop_reason
        super().__init__(f"model response did not complete normally: stopReason={stop_reason!r}")


class UnexpectedStopReason(Exception):
    """Raised when Bedrock's stopReason is anything other than the one
    successful value this call expected — e.g. guardrail_intervened,
    content_filtered, malformed_model_output, malformed_tool_use, or
    model_context_window_exceeded. Codex review 2026-09-16 confirmed (via
    AWS's own Converse docs) that stopReason has 9 possible values and the
    original _check_stop_reason only ever checked for one of them
    (max_tokens) — every other abnormal value fell through and got treated
    as if the response were trustworthy."""

    def __init__(self, stop_reason: str | None, expected: str) -> None:
        self.stop_reason = stop_reason
        self.expected = expected
        super().__init__(f"expected stopReason={expected!r}, got {stop_reason!r}")


class ToolCallMissing(Exception):
    """Raised when a forced tool-use Converse call didn't come back with
    exactly one matching toolUse content block — none (e.g. the model
    text-answered instead) or more than one (ambiguous which call is the
    real answer; the original code silently used whichever came first)."""


@dataclass
class BedrockReasoningClient:
    """Claude via Bedrock — the core reasoning/synthesis engine (ADR-0006)."""

    model_id: str
    region_name: str = "us-east-1"

    def __post_init__(self) -> None:
        self._client = boto3.client("bedrock-runtime", region_name=self.region_name)

    @staticmethod
    def _check_stop_reason(response: dict[str, Any], expected: str) -> None:
        # Fails closed unless stopReason is exactly the one value this call
        # expected on success, rather than only ever checking for
        # max_tokens (Codex review 2026-09-16, confirmed against AWS's
        # Converse docs: the real value set is end_turn, tool_use,
        # max_tokens, stop_sequence, guardrail_intervened,
        # content_filtered, malformed_model_output, malformed_tool_use,
        # model_context_window_exceeded — 5 of those 9 previously fell
        # through unchecked and got treated as a trustworthy response).
        stop_reason = response.get("stopReason")
        if stop_reason == expected:
            return
        if stop_reason == "max_tokens":
            raise ModelOutputTruncated(stop_reason)
        raise UnexpectedStopReason(stop_reason, expected)

    def converse(self, system_prompt: str, user_content: str, max_tokens: int) -> str:
        response = self._client.converse(
            modelId=self.model_id,
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": [{"text": user_content}]}],
            inferenceConfig={"maxTokens": max_tokens},
        )
        self._check_stop_reason(response, expected="end_turn")
        content_blocks = response["output"]["message"]["content"]
        for block in content_blocks:
            if "text" in block:
                return block["text"]
        raise ToolCallMissing(f"no text content block in response: {response!r}")

    def converse_structured(
        self,
        system_prompt: str,
        user_content: str,
        max_tokens: int,
        tool_name: str,
        tool_description: str,
        input_schema: dict[str, Any],
    ) -> Any:
        """Forces the model to respond via a single tool call whose input
        must match `input_schema`, instead of free-form text.

        This is the standard Anthropic tool-use pattern, not Bedrock's
        native/version-specific "structured output" flag — Converse's
        toolChoice can force a specific tool on every Claude model Bedrock
        exposes via this API, so this path isn't tied to what Sonnet
        version happens to be configured (relevant while Sonnet 4.6 is a
        documented temporary stand-in for Sonnet 5, see
        validate_reason_node.py). It also means the model's answer is
        boto3's already-parsed dict/list, not a JSON string — no more
        stripping a ```json fence, since tool input is never markdown.

        `strict: True` is a real, documented ToolSpecification field
        (confirmed 2026-09-16 against AWS's own API reference, not just
        Codex's claim) that enforces the tool input actually matches
        `input_schema` server-side, instead of relying on the model's
        prompt compliance — this is what stops a previously-seen
        alternative-shape variant (e.g. {alternative, rationale} instead
        of {option, reason_rejected}) from ever reaching application code.
        Not confirmed which exact models honor it on Bedrock yet (AWS's
        own blog post names a "select providers" list including Anthropic
        but doesn't enumerate Sonnet 4.6 specifically) — if a live call
        ever 400s citing `strict` as unsupported for this model_id, that's
        the signal to make this conditional per-model, not a reason to
        guess now and add untested conditional logic.
        """
        response = self._client.converse(
            modelId=self.model_id,
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": [{"text": user_content}]}],
            inferenceConfig={"maxTokens": max_tokens},
            toolConfig={
                "tools": [
                    {
                        "toolSpec": {
                            "name": tool_name,
                            "description": tool_description,
                            "inputSchema": {"json": input_schema},
                            "strict": True,
                        }
                    }
                ],
                "toolChoice": {"tool": {"name": tool_name}},
            },
        )
        self._check_stop_reason(response, expected="tool_use")
        content_blocks = response["output"]["message"]["content"]
        matches = [
            block["toolUse"]
            for block in content_blocks
            if block.get("toolUse", {}).get("name") == tool_name
        ]
        if len(matches) == 1:
            return matches[0]["input"]
        if len(matches) == 0:
            raise ToolCallMissing(f"no {tool_name!r} tool call in response: {response!r}")
        # More than one matching call is ambiguous — the original code
        # silently returned whichever came first, discarding the rest
        # (Codex review 2026-09-16). Fail loud instead of guessing.
        raise ToolCallMissing(
            f"expected exactly one {tool_name!r} tool call, got {len(matches)}: {response!r}"
        )


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
