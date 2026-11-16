"""Versioned request measurement for the small-workload pilot.

Measures the complete application request, then uses unbilled CountTokens
for the generation cost estimate. See docs/p2-request-budget.md for evidence
and limits of this pilot policy.
"""

import json
import math
import time
from dataclasses import dataclass, field
from typing import Any

REQUEST_MEASUREMENT_VERSION = "converse-request-json@1"
POLICY_VERSION = "review-request-budget@2026-11-16"
MAX_REQUEST_BYTES = 86 * 1024
MAX_EVIDENCE_BYTES = 42 * 1024
DEEPER_EVIDENCE_BYTES = 20 * 1024
MODEL_ID = "us.anthropic.claude-sonnet-4-6"
COUNT_MODEL_ID = "anthropic.claude-sonnet-4-6"


class RequestBudgetExceeded(ValueError):
    """A dispatch stopped before generation; earlier screening may be billed."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def structured_request(
    model_id, system_prompt, user_content, max_tokens, tool_name, tool_description, input_schema
) -> dict:
    return {
        "modelId": model_id,
        "system": [{"text": system_prompt}],
        "messages": [{"role": "user", "content": [{"text": user_content}]}],
        "inferenceConfig": {"maxTokens": max_tokens},
        "toolConfig": {
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
    }


def count_input_tokens(client: Any, request: dict) -> int:
    """Bedrock's unbilled CountTokens, covering system, messages and tool schema."""
    if request.get("modelId") != MODEL_ID:
        raise RequestBudgetExceeded("unsupported_budget_model")
    try:
        result = client.count_tokens(
            # CountTokens targets the underlying foundation model, not the
            # cross-region inference profile used by Converse generation.
            modelId=COUNT_MODEL_ID,
            input={"converse": {k: request[k] for k in ("system", "messages", "toolConfig")}},
        )
    except Exception as exc:
        raise RequestBudgetExceeded("token_count_unavailable") from exc
    count = result.get("inputTokens") if isinstance(result, dict) else None
    if type(count) is not int or count < 0:
        raise RequestBudgetExceeded("token_count_unavailable")
    return count


def generation_cost_micro_usd(input_tokens: int, output_tokens: int) -> int:
    # Existing US Sonnet 4.6 reservation rates, versioned with this policy.
    # Estimates, not a whole-account invoice guarantee. No caching is requested.
    return math.ceil((input_tokens * 33 + output_tokens * 165) / 10)


def evidence_bytes(chunks: list[dict]) -> int:
    """Contribution inside the JSON user string, including its outer escaping."""
    evidence = [
        {"chunk_id": c.get("chunk_id"), "source": c.get("heading_path"), "text": c.get("text")}
        for c in chunks
    ]
    fragment = json.dumps(evidence, separators=(",", ":"))
    return len(json.dumps(fragment, ensure_ascii=False).encode("utf-8")) - 2


def evidence_limit(deep: bool) -> int:
    return DEEPER_EVIDENCE_BYTES if deep else MAX_EVIDENCE_BYTES


@dataclass
class GenerationBudget:
    operation: str
    reservation: int
    deadline: float
    clock: Any = time.monotonic
    verification_enabled: bool = False
    reserved_generation: int = field(default=0, init=False)
    dispatched: int = field(default=0, init=False)
    reserved_output_tokens: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        ceiling = 200000 if self.operation.startswith("deeper:") else 400000
        if type(self.reservation) is not int or not 0 < self.reservation <= ceiling:
            raise RequestBudgetExceeded("analysis_cost_limit_exceeded")

    @property
    def other_allowance(self) -> int:
        return 10000 if self.operation.startswith("deeper:") else 20000

    def check_deadline(self) -> None:
        if self.clock() >= self.deadline:
            raise RequestBudgetExceeded("analysis_dispatch_limit")

    def admit(self, request: dict, client: Any) -> None:
        experimental = self.verification_enabled and not self.operation.startswith("deeper:")
        if self.clock() >= self.deadline or self.dispatched >= (2 if experimental else 1):
            raise RequestBudgetExceeded("analysis_dispatch_limit")
        if request_utf8_bytes(request) > MAX_REQUEST_BYTES:
            raise RequestBudgetExceeded("analysis_input_limit_exceeded")
        maximum = (
            (8192 if self.dispatched == 0 else 4096)
            if experimental
            else (4096 if self.operation.startswith("deeper:") else 12288)
        )
        if experimental:
            expected = "emit_findings" if self.dispatched == 0 else "verify_findings"
            name = request.get("toolConfig", {}).get("toolChoice", {}).get("tool", {}).get("name")
            if name != expected:
                raise RequestBudgetExceeded("analysis_dispatch_limit")
        tokens = request.get("inferenceConfig", {}).get("maxTokens")
        if type(tokens) is not int or not 0 < tokens <= maximum:
            raise RequestBudgetExceeded("analysis_output_limit_exceeded")
        if self.reserved_output_tokens + tokens > 12288:
            raise RequestBudgetExceeded("analysis_output_limit_exceeded")
        count = count_input_tokens(client, request)
        cost = generation_cost_micro_usd(count, tokens)
        if cost + self.reserved_generation + self.other_allowance > self.reservation:
            raise RequestBudgetExceeded("analysis_cost_limit_exceeded")
        if self.clock() >= self.deadline:
            raise RequestBudgetExceeded("analysis_dispatch_limit")
        # Retain this maximum on timeouts/unknown usage; never retry generation.
        self.reserved_generation += cost
        self.reserved_output_tokens += tokens
        self.dispatched += 1


def request_utf8_bytes(request: dict[str, Any]) -> int:
    """Canonical JSON bytes including model, system, messages, tools and config."""
    return len(
        json.dumps(
            request, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    )
