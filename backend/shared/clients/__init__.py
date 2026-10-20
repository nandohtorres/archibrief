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
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.types import TypeSerializer
from botocore.config import Config
from botocore.exceptions import ClientError


def _dynamodb_safe(value: Any) -> Any:
    """boto3's DynamoDB resource layer (Table.put_item) rejects a native
    Python float outright (`TypeError: Float types are not supported`) —
    found 2026-10-01 writing deeper_review.handler, the first call site in
    this codebase to ever put_item a Finding dict (every prior put_item
    call — Reviews pointer items, AuditLog records — happened to have no
    float fields, so this never surfaced before). DynamoDB's own Number
    type is exact/arbitrary-precision, which boto3 models as Decimal, not
    float — `Decimal(str(value))` avoids float's own binary-representation
    imprecision (`Decimal(0.1) != Decimal("0.1")`)."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _dynamodb_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_dynamodb_safe(v) for v in value]
    return value


def _timeouts(
    read_timeout_seconds: float | None, connect_timeout_seconds: float | None, no_retries: bool
) -> dict[str, Any]:
    """boto3.client kwargs for a bounded call. All unset = botocore's
    defaults (60 s timeouts, retries), which is what the review pipeline
    uses. The chat bounds every call so the sum fits its 28 s Lambda
    (code review 2026-10-16)."""
    config_kwargs: dict[str, Any] = {}
    if read_timeout_seconds is not None:
        config_kwargs["read_timeout"] = read_timeout_seconds
    if connect_timeout_seconds is not None:
        config_kwargs["connect_timeout"] = connect_timeout_seconds
    if no_retries:
        # botocore's "max_attempts" counts retries only; "total_max_attempts"
        # counts the first call too.
        config_kwargs["retries"] = {"total_max_attempts": 1, "mode": "standard"}
    return {"config": Config(**config_kwargs)} if config_kwargs else {}


@dataclass
class DynamoDBClient:
    table_name: str
    region_name: str = "us-east-1"

    def __post_init__(self) -> None:
        self._resource = boto3.resource("dynamodb", region_name=self.region_name)
        self._table = self._resource.Table(self.table_name)

    def put_item(self, item: dict[str, Any]) -> None:
        self._table.put_item(Item=_dynamodb_safe(item))

    def get_item(self, key: dict[str, Any]) -> dict[str, Any] | None:
        response = self._table.get_item(Key=key)
        return response.get("Item")

    def query(self, **kwargs: Any) -> list[dict[str, Any]]:
        response = self._table.query(**kwargs)
        return response.get("Items", [])

    def update_item(self, **kwargs: Any) -> None:
        """Field-level update (with an optional ConditionExpression), so
        callers don't overwrite fields written concurrently by others —
        unlike put_item, which replaces the whole item."""
        self._table.update_item(**kwargs)


@dataclass
class S3Client:
    bucket: str
    region_name: str = "us-east-1"

    def __post_init__(self) -> None:
        # Explicit SigV4 — found 2026-10-12 live-testing ADR-0045's upload
        # flow: without it, boto3 generated a presigned POST against the
        # legacy global s3.amazonaws.com endpoint, which S3 rejected with
        # "Requests specifying Server Side Encryption with AWS KMS managed
        # keys require AWS Signature Version 4" (this bucket's default
        # encryption is aws:kms — infra/modules/s3/main.tf). SigV4 is
        # required unconditionally for any presigned request against a
        # KMS-encrypted bucket, so this isn't optional even though boto3
        # doesn't default to it here.
        self._client = boto3.client(
            "s3",
            region_name=self.region_name,
            config=Config(signature_version="s3v4"),
        )

    def put_object(self, key: str, body: bytes, content_type: str = "application/json") -> None:
        self._client.put_object(Bucket=self.bucket, Key=key, Body=body, ContentType=content_type)

    def get_object(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()

    def generate_presigned_post(
        self,
        key: str,
        max_bytes: int,
        expires_in: int = 900,
        content_type: str = "application/x-tar",
    ) -> dict[str, Any]:
        """Used by create_upload.handler (2026-10-12, archive_path/upload
        design) — a presigned POST, not a bare presigned PUT, specifically
        because a POST's `Conditions` let S3 itself enforce a byte-size
        ceiling (`content-length-range`) and content type before accepting
        the object, instead of trusting the client to send a reasonably
        sized file. Matches this project's established pattern of bounding
        untrusted input at the earliest possible point (extract_archive's
        own member-count/path-traversal/symlink checks, the 400 KB
        DynamoDB item cap) rather than relying on a later stage to reject
        an oversized upload after it's already landed in S3."""
        return self._client.generate_presigned_post(
            Bucket=self.bucket,
            Key=key,
            Fields={"Content-Type": content_type},
            Conditions=[
                {"Content-Type": content_type},
                ["content-length-range", 0, max_bytes],
            ],
            ExpiresIn=expires_in,
        )


@dataclass
class S3VectorsClient:
    """Wraps AWS S3 Vectors (ADR-0007) — a rebuildable index, not source of truth."""

    bucket_name: str
    index_name: str
    region_name: str = "us-east-1"
    read_timeout_seconds: float | None = None
    connect_timeout_seconds: float | None = None
    no_retries: bool = False

    def __post_init__(self) -> None:
        self._client = boto3.client(
            "s3vectors",
            region_name=self.region_name,
            **_timeouts(self.read_timeout_seconds, self.connect_timeout_seconds, self.no_retries),
        )

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
    read_timeout_seconds: float | None = None
    connect_timeout_seconds: float | None = None
    no_retries: bool = False

    def __post_init__(self) -> None:
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=self.region_name,
            **_timeouts(self.read_timeout_seconds, self.connect_timeout_seconds, self.no_retries),
        )

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
    # Both None = botocore's defaults (the review runtime). The chat sets a
    # read timeout under its API's 30 s limit and no retries, since a
    # retried call after a timeout would be a second paid call (ADR-0050).
    read_timeout_seconds: float | None = None
    no_retries: bool = False
    connect_timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=self.region_name,
            **_timeouts(self.read_timeout_seconds, self.connect_timeout_seconds, self.no_retries),
        )

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

    def converse_tool_cached(
        self,
        system_prompt: str,
        cached_user_text: str,
        user_text: str,
        max_tokens: int,
        tool_name: str,
        tool_description: str,
        input_schema: dict[str, Any],
    ) -> tuple[Any, dict[str, int]]:
        """converse_structured for the chat (ADR-0050): the same forced,
        strict tool call, plus prompt caching and token usage.

        Cache points sit after the system prompt and after
        `cached_user_text` (the review block, the same for every question
        on a review), so later questions read that prefix from cache.
        `user_text` (history, retrieved chunks, the question) follows
        uncached in the same user message. A prefix under the model's
        minimum cacheable size simply isn't cached; the call still works.

        Returns (tool input, usage), where usage has inputTokens,
        outputTokens, cacheReadInputTokens and cacheWriteInputTokens
        (0 when absent).
        """
        response = self._client.converse(
            modelId=self.model_id,
            system=[{"text": system_prompt}, {"cachePoint": {"type": "default"}}],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"text": cached_user_text},
                        {"cachePoint": {"type": "default"}},
                        {"text": user_text},
                    ],
                }
            ],
            inferenceConfig={"maxTokens": max_tokens, "temperature": 0},
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
        raw_usage = response.get("usage") or {}
        usage = {
            key: int(raw_usage.get(key) or 0)
            for key in (
                "inputTokens",
                "outputTokens",
                "cacheReadInputTokens",
                "cacheWriteInputTokens",
            )
        }
        matches = [
            block["toolUse"]
            for block in response["output"]["message"]["content"]
            if block.get("toolUse", {}).get("name") == tool_name
        ]
        if len(matches) != 1:
            raise ToolCallMissing(
                f"expected exactly one {tool_name!r} tool call, got {len(matches)}"
            )
        return matches[0]["input"], usage


@dataclass
class GuardrailVerdict:
    """What one ApplyGuardrail input check decided. `filters` names what
    fired (e.g. "PROMPT_ATTACK", "topic:OtherUsersData"), never content."""

    blocked: bool
    filters: list[str]


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
    read_timeout_seconds: float | None = None
    connect_timeout_seconds: float | None = None
    no_retries: bool = False

    def __post_init__(self) -> None:
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=self.region_name,
            **_timeouts(self.read_timeout_seconds, self.connect_timeout_seconds, self.no_retries),
        )

    def check(self, text: str, source: str = "INPUT") -> bool:
        response = self._client.apply_guardrail(
            guardrailIdentifier=self.guardrail_id,
            guardrailVersion=self.guardrail_version,
            source=source,
            content=[{"text": {"text": text}}],
        )
        return response["action"] == "NONE"

    def assess(self, text: str) -> GuardrailVerdict:
        """check(), plus which filters fired, for the chat's stage-7 log
        (ADR-0050). Fails closed: any action other than NONE is a block."""
        response = self._client.apply_guardrail(
            guardrailIdentifier=self.guardrail_id,
            guardrailVersion=self.guardrail_version,
            source="INPUT",
            content=[{"text": {"text": text}}],
        )
        filters: list[str] = []
        for assessment in response.get("assessments") or []:
            for item in (assessment.get("contentPolicy") or {}).get("filters") or []:
                if item.get("action") == "BLOCKED":
                    filters.append(str(item.get("type", "content")))
            for item in (assessment.get("topicPolicy") or {}).get("topics") or []:
                if item.get("action") == "BLOCKED":
                    filters.append(f"topic:{item.get('name', 'unknown')}")
        return GuardrailVerdict(blocked=response.get("action") != "NONE", filters=filters)

    def grounding_scores(self, source: str, query: str, answer: str) -> dict[str, float]:
        """Contextual grounding scores for an answer ({"GROUNDING": 0.8,
        "RELEVANCE": 0.9}), for detect-only logging (ADR-0050 §4). The
        caller never blocks on these."""
        response = self._client.apply_guardrail(
            guardrailIdentifier=self.guardrail_id,
            guardrailVersion=self.guardrail_version,
            source="OUTPUT",
            content=[
                {"text": {"text": source, "qualifiers": ["grounding_source"]}},
                {"text": {"text": query, "qualifiers": ["query"]}},
                {"text": {"text": answer, "qualifiers": ["guard_content"]}},
            ],
        )
        scores: dict[str, float] = {}
        for assessment in response.get("assessments") or []:
            policy = assessment.get("contextualGroundingPolicy") or {}
            for item in policy.get("filters") or []:
                if "type" in item and "score" in item:
                    scores[str(item["type"])] = float(item["score"])
        return scores


class TransactionCanceled(Exception):
    """A DynamoDB transaction was cancelled. `reasons` has one code per
    action, in order ("None" for an action that wasn't the cause)."""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__(f"transaction cancelled: {reasons}")


@dataclass
class DynamoDBTransactionClient:
    """TransactWriteItems over plain Python values (ADR-0050's chat
    admission: the per-review counter, the question record and the global
    budget reservation succeed or fail together).

    Each action is {"Put"|"Update": {...}} in the low-level API's shape,
    except that Key, Item and ExpressionAttributeValues hold plain Python
    values; they're serialized here.
    """

    region_name: str = "us-east-1"

    def __post_init__(self) -> None:
        self._client = boto3.client("dynamodb", region_name=self.region_name)
        self._serializer = TypeSerializer()

    def _serialize(self, values: dict[str, Any]) -> dict[str, Any]:
        return {k: self._serializer.serialize(_dynamodb_safe(v)) for k, v in values.items()}

    def transact_write(self, actions: list[dict[str, Any]]) -> None:
        items = []
        for action in actions:
            ((kind, body),) = action.items()
            body = dict(body)
            for field in ("Key", "Item", "ExpressionAttributeValues"):
                if field in body:
                    body[field] = self._serialize(body[field])
            items.append({kind: body})
        try:
            self._client.transact_write_items(TransactItems=items)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "TransactionCanceledException":
                raise
            raise TransactionCanceled(_cancellation_reasons(exc, len(items))) from exc


def _cancellation_reasons(exc: Any, count: int) -> list[str]:
    """CancellationReasons from the response, or parsed from the message
    ("... reasons [ConditionalCheckFailed, None]") when only that is set."""
    reasons = exc.response.get("CancellationReasons")
    if reasons:
        return [str(r.get("Code", "None")) for r in reasons]
    message = exc.response.get("Error", {}).get("Message", "")
    match = re.search(r"\[([^\]]*)\]", message)
    if match:
        parsed = [part.strip() for part in match.group(1).split(",")]
        if len(parsed) == count:
            return parsed
    return ["Unknown"] * count


@dataclass
class AgentCoreRuntimeClient:
    """Invokes a deployed Bedrock AgentCore Runtime directly over boto3 —
    used by deeper_review.handler (2026-10-01) for the "go deeper" path,
    which bypasses Step Functions entirely (ADR-0023/ADR-0039: a scoped
    per-finding re-run, not a full pipeline execution). The outer review
    pipeline instead goes through Step Functions' own SDK integration
    (`arn:aws:states:::aws-sdk:bedrockagentcore:invokeAgentRuntime`,
    infra/modules/step-functions-lambda) — this wrapper is for callers
    that need the same operation from a Lambda, not from ASL.

    boto3's `bedrock-agentcore` client and its `invoke_agent_runtime`
    operation were confirmed to exist against the installed botocore
    service model 2026-10-01 (not guessed): required params
    `agentRuntimeArn` (string) and `payload` (blob); the response's
    `response` field is a blob (a `StreamingBody`, read once)."""

    agent_runtime_arn: str
    region_name: str = "us-east-1"
    # None = botocore's default. Callers behind a synchronous API set this
    # below their gateway's timeout (Codex F19).
    read_timeout_seconds: int | None = None

    def __post_init__(self) -> None:
        # Never auto-retry: a retried invocation after a read timeout would
        # start a second paid reasoning run for the same request.
        # botocore's "max_attempts" counts retries only; "total_max_attempts"
        # includes the first call, so 1 means exactly one attempt.
        config_kwargs: dict[str, Any] = {"retries": {"total_max_attempts": 1, "mode": "standard"}}
        if self.read_timeout_seconds is not None:
            config_kwargs["read_timeout"] = self.read_timeout_seconds
        self._client = boto3.client(
            "bedrock-agentcore", region_name=self.region_name, config=Config(**config_kwargs)
        )

    def invoke(self, payload: dict[str, Any], runtime_session_id: str) -> dict[str, Any]:
        response = self._client.invoke_agent_runtime(
            agentRuntimeArn=self.agent_runtime_arn,
            runtimeSessionId=runtime_session_id,
            payload=json.dumps(payload).encode("utf-8"),
        )
        return json.loads(response["response"].read())
