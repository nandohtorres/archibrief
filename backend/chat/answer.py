"""Answer one question about one review: retrieve, one model call, verify.

The paid part of a chat request, shared by the ask_question Lambda and
the chat eval (ADR-0050 §1). Model-call failures propagate for the caller
to map (timeout → 504, truncated or malformed output → 502); retrieval
and the detect-only grounding check fail open, because neither can make
an answer less grounded: without chunks the model can only cite the
review itself.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from backend.agent.nodes.retrieve import vector_search
from backend.chat.context import ReviewContext
from backend.chat.pricing import GROUNDING_MICRO_USD_PER_UNIT, model_cost_micro_usd, text_units
from backend.chat.prompt import (
    ANSWER_SCHEMA,
    MAX_OUTPUT_TOKENS,
    TOOL_DESCRIPTION,
    TOOL_NAME,
    build_system_prompt,
    build_turn_text,
    history_for_prompt,
)
from backend.chat.verify import VerifiedAnswer, verify_answer
from backend.shared.clients import (
    BedrockEmbeddingClient,
    BedrockReasoningClient,
    GuardrailsClient,
    S3VectorsClient,
)

RETRIEVED_CHUNKS = 3
GROUNDING_SOURCE_CHARS = 20000
# Worst case for the grounding call (connect + read timeout the Lambda
# sets on it). With less time than this left, the detect-only check is
# skipped rather than risk the Lambda being killed mid-request.
GROUNDING_WORST_SECONDS = 5.0
# The model call's read timeout under a deadline: whatever time is left
# after retrieval, up to MODEL_READ_TIMEOUT_SECONDS. Sized after retrieval,
# not before, so the model doesn't give up seconds to retrieval's worst
# case (Sonnet answers take 15-19 s).
MODEL_READ_TIMEOUT_SECONDS = 24.0
MIN_MODEL_READ_TIMEOUT_SECONDS = 5.0
MODEL_CONNECT_TIMEOUT_SECONDS = 1.0


def model_read_timeout(deadline: float) -> float:
    left = deadline - time.monotonic() - MODEL_CONNECT_TIMEOUT_SECONDS
    return max(MIN_MODEL_READ_TIMEOUT_SECONDS, min(MODEL_READ_TIMEOUT_SECONDS, left))


@dataclass
class ChatClients:
    # A ready model client (the eval, tests), or make_reasoning, which
    # builds one with a read timeout once the time left is known.
    reasoning: BedrockReasoningClient | None = None
    embedding: BedrockEmbeddingClient | None = None
    vectors: S3VectorsClient | None = None
    # The contextual-grounding guardrail; None turns the check off.
    grounding: GuardrailsClient | None = None
    make_reasoning: Callable[[float], BedrockReasoningClient] | None = None


@dataclass
class AnswerResult:
    answer: VerifiedAnswer
    usage: dict[str, int]
    cost_micro_usd: int
    retrieved_chunks: int
    grounding: dict[str, float] = field(default_factory=dict)
    latency_ms: int = 0


def retrieve_chunks(question: str, focus_category: str, clients: ChatClients) -> list[dict]:
    if clients.embedding is None or clients.vectors is None:
        return []
    query = f"{focus_category}: {question}" if focus_category else question
    try:
        results = vector_search(
            query[:1000], clients.embedding, clients.vectors, top_k=RETRIEVED_CHUNKS
        )
    except Exception:  # noqa: BLE001 - retrieval fails open (module docstring)
        return []
    chunks = []
    for i, chunk in enumerate(results[:RETRIEVED_CHUNKS], start=1):
        if not chunk.text:
            continue
        chunks.append(
            {
                "ref": f"R{i}",
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "heading_path": chunk.heading_path,
                "source_url": chunk.source_url,
            }
        )
    return chunks


def answer_question(
    ctx: ReviewContext,
    question: str,
    history: list[dict[str, Any]],
    focus_alias: str | None,
    clients: ChatClients,
    canary: str,
    deadline: float | None = None,
) -> AnswerResult:
    """`deadline` is a time.monotonic() value the request must finish by
    (the Lambda's remaining time); None means no limit (the eval)."""
    started = time.monotonic()
    chunks = retrieve_chunks(question, ctx.finding_categories.get(focus_alias or "", ""), clients)
    if clients.make_reasoning is not None and deadline is not None:
        reasoning = clients.make_reasoning(model_read_timeout(deadline))
    elif clients.reasoning is not None:
        reasoning = clients.reasoning
    else:
        raise ValueError("ChatClients needs reasoning, or make_reasoning and a deadline")
    raw, usage = reasoning.converse_tool_cached(
        system_prompt=build_system_prompt(canary),
        cached_user_text=ctx.cached_text(),
        user_text=build_turn_text(question, history_for_prompt(history), chunks, focus_alias),
        max_tokens=MAX_OUTPUT_TOKENS,
        tool_name=TOOL_NAME,
        tool_description=TOOL_DESCRIPTION,
        input_schema=ANSWER_SCHEMA,
    )
    verified = verify_answer(raw, ctx, {c["ref"]: c for c in chunks}, canary)
    cost = model_cost_micro_usd(reasoning.model_id, usage)

    grounding: dict[str, float] = {}
    time_left = deadline is None or deadline - time.monotonic() >= GROUNDING_WORST_SECONDS
    if (
        clients.grounding is not None
        and time_left
        and verified.status == "answered"
        and verified.cited_text
    ):
        source = "\n\n".join(verified.cited_text)[:GROUNDING_SOURCE_CHARS]
        answer_text = "\n\n".join(p["text"] for p in verified.paragraphs)
        try:
            grounding = clients.grounding.grounding_scores(source, question[:1000], answer_text)
            cost += GROUNDING_MICRO_USD_PER_UNIT * text_units(
                len(source) + len(question) + len(answer_text)
            )
        except Exception:  # noqa: BLE001 - detect-only; never blocks an answer
            grounding = {}

    return AnswerResult(
        answer=verified,
        usage=usage,
        cost_micro_usd=cost,
        retrieved_chunks=len(chunks),
        grounding=grounding,
        latency_ms=int((time.monotonic() - started) * 1000),
    )
