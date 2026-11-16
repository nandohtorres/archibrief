"""AgentCore Runtime entrypoint for the PreflightGate -> Retrieve -> Reason
subworkflow (ADR-0028).

This is what infra/modules/agentcore-runtime deploys and what Step Functions'
InvokeAgent task (infra/modules/step-functions-lambda) calls. Everything before
(Ingest, RuleEngine) and after (Validate, Audit, Finalize) stays outside this
entrypoint entirely, as bounded Lambda work Step Functions orchestrates
directly (ADR-0028) — this file owns exactly the LangGraph subworkflow and
nothing else.

Standard AgentCore pattern (BedrockAgentCoreApp + @app.entrypoint): the
compiled graph and every real AWS client it needs are built ONCE at
import/module time, not per-invocation, so a warm process reuses them across
requests. AgentCore does not promise reuse across cold starts, so nothing here
assumes state survives a cold start that wasn't explicitly rebuilt from these
module-level singletons.

Published examples cover LangGraph on AgentCore via container deployment,
and ZIP/code deployment via Terraform for non-LangGraph agents, but not
this exact combination (LangGraph + ZIP/code_configuration + native
Terraform aws_bedrockagentcore_agent_runtime). The entrypoint contract
below (input/output shape, exception propagation) follows AWS's documented
AgentCore patterns.
"""

from __future__ import annotations

import copy
import os
import time
from typing import Any

import boto3
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from botocore.config import Config

from backend.agent.graph import ReviewState, compiled_deeper_graph, compiled_graph
from backend.corpus.lexical_index import build_lexical_corpus_index_from_disk
from backend.shared.admission import AdmissionDenied
from backend.shared.clients import (
    BedrockEmbeddingClient,
    BedrockReasoningClient,
    GuardrailsClient,
    S3VectorsClient,
)
from backend.shared.model_request_budget import GenerationBudget, RequestBudgetExceeded
from backend.shared.scope_admission import authorize_payload, checked_request_envelope

_REGION = os.environ.get("AWS_REGION", "us-east-1")
_VECTOR_BUCKET_NAME = os.environ.get("ARCHIBRIEF_VECTOR_BUCKET", "archibrief-dev-kb")
_VECTOR_INDEX_NAME = os.environ.get("ARCHIBRIEF_VECTOR_INDEX", "archibrief-dev-kb-index")
_GUARDRAIL_ID = os.environ.get("ARCHIBRIEF_GUARDRAIL_ID", "")
_GUARDRAIL_VERSION = os.environ.get("ARCHIBRIEF_GUARDRAIL_VERSION", "1")

# The model ID comes from an env var so it can change without a code
# change; the default matches the other call sites.
_MODEL_ID = os.environ.get("ARCHIBRIEF_REASONING_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
_MAX_TOKENS = int(os.environ.get("ARCHIBRIEF_REASONING_MAX_TOKENS", "12288"))
_TOKEN_COUNTER = boto3.client(
    "bedrock-runtime",
    region_name=_REGION,
    config=Config(
        connect_timeout=2,
        read_timeout=15,
        retries={"total_max_attempts": 1},
    ),
)

app = BedrockAgentCoreApp()

# Built once at import time, reused across a warm process — see module
# docstring. build_lexical_corpus_index_from_disk() reads backend/corpus/
# JSON data files that must ship inside the deployment artifact (see
# build_runtime_package.py).
_GRAPH = compiled_graph()
# "Go deeper": same deployed AgentCore Runtime, same
# module-level singletons — a second graph object, not a second deployed
# runtime, since nothing here needs a different Bedrock model/IAM role,
# only a different wiring of the same nodes (build_deeper_graph's own
# docstring explains why).
_DEEPER_GRAPH = compiled_deeper_graph()
_EMBEDDING_CLIENT = BedrockEmbeddingClient(region_name=_REGION, no_retries=True)
_VECTORS_CLIENT = S3VectorsClient(
    bucket_name=_VECTOR_BUCKET_NAME,
    index_name=_VECTOR_INDEX_NAME,
    region_name=_REGION,
    no_retries=True,
)
_LEXICAL_CORPUS_INDEX = build_lexical_corpus_index_from_disk()
_GUARDRAILS_CLIENT = GuardrailsClient(
    guardrail_id=_GUARDRAIL_ID,
    guardrail_version=_GUARDRAIL_VERSION,
    region_name=_REGION,
    no_retries=True,
)
# One non-streaming call that waits for the complete answer. Bedrock holds
# a forced, strict tool call's output until it is finished, so a streamed
# call showed 90 s of silence on healthy reviews and an idle limit cut them
# off (2026-10-29). The read timeout is therefore the whole-answer wait:
# long enough for a large review (the slowest measured call took 112 s),
# and with retrieval it stays below the 600 s the review worker waits for
# this runtime, so a slow call ends here first and the worker can still
# publish the rule findings.
_REASONING_READ_TIMEOUT_SECONDS = float(
    os.environ.get("ARCHIBRIEF_REASONING_READ_TIMEOUT_SECONDS", "400")
)
_REASONING_CLIENT = BedrockReasoningClient(
    model_id=_MODEL_ID,
    region_name=_REGION,
    no_retries=True,
    read_timeout_seconds=_REASONING_READ_TIMEOUT_SECONDS,
)
# "Go deeper" re-reviews one finding, so its answer is short, and its worker
# waits only 300 s for this runtime.
_DEEPER_REASONING_READ_TIMEOUT_SECONDS = float(
    os.environ.get("ARCHIBRIEF_DEEPER_REASONING_READ_TIMEOUT_SECONDS", "240")
)
_DEEPER_REASONING_CLIENT = BedrockReasoningClient(
    model_id=_MODEL_ID,
    region_name=_REGION,
    no_retries=True,
    read_timeout_seconds=_DEEPER_REASONING_READ_TIMEOUT_SECONDS,
)


def _budget_client(payload: dict, client: BedrockReasoningClient) -> BedrockReasoningClient:
    row = checked_request_envelope(payload)
    result = copy.copy(client)
    result.token_counter = _TOKEN_COUNTER
    remaining = min(400, float(row["analysis_deadline"]) - time.time())
    result.generation_budget = GenerationBudget(
        payload["review_scope_ref"]["operation"],
        int(row["cost"]),
        time.monotonic() + remaining,
        verification_enabled=(
            payload.get("mode") != "deeper"
            and os.environ.get("ARCHIBRIEF_VERIFY_FINDINGS", "false") == "true"
        ),
    )
    return result


def _log_refusal(where: str, exc: Exception, payload: dict, client: Any = None) -> None:
    """One plain log line for every refused or bounded review; no review text."""
    import json

    budget = getattr(client, "generation_budget", None)
    print(
        json.dumps(
            {
                "event": "review_refused",
                "where": where,
                "review_id": payload.get("review_id"),
                "mode": payload.get("mode", "initial"),
                "type": type(exc).__name__,
                "code": getattr(exc, "code", None),
                "cause": type(exc.__cause__).__name__ if exc.__cause__ else None,
                "cause_message": str(exc.__cause__)[:300] if exc.__cause__ else None,
                "dispatched": getattr(budget, "dispatched", None),
                "reserved_generation": getattr(budget, "reserved_generation", None),
                "reserved_output_tokens": getattr(budget, "reserved_output_tokens", None),
                "reservation": getattr(budget, "reservation", None),
                "verification_enabled": getattr(budget, "verification_enabled", None),
            },
            default=str,
        )
    )


def _bounded_result(payload: dict, code: str) -> dict:
    from backend.agent.nodes.preflight import preflight_node

    fields = {} if payload.get("mode") == "deeper" else preflight_node(payload)
    return {
        "status": "complete",
        "findings": payload.get("rule_findings", []),
        "model_outcome": "not_invoked",
        "budget_reason": code,
        "model_output_counts": {"attempted": 0, "accepted": 0, "rejected": 0},
        "preflight_fields": fields.get("preflight_fields", {}),
        "defaults_version": fields.get("defaults_version"),
    }


def _invoke_deeper(payload: dict[str, Any]) -> dict[str, Any]:
    """Go-deeper pass: Retrieve -> Reason(deep) only, scoped to one
    finding. Called by deeper_review.handler (behind
    POST /reviews/{reviewId}/findings/{findingId}/deeper), never by the
    outer Step Functions state machine. PreflightGate is not rerun;
    the original settled requirements and resource observations are reused.
    """
    try:
        admission = authorize_payload(payload)
        reasoning_client = _budget_client(payload, _DEEPER_REASONING_CLIENT)
    except AdmissionDenied as exc:
        return {"status": "admission_denied", "code": exc.code}
    initial_state: ReviewState = {
        "paid_scope_context": admission,
        "generation_budget": reasoning_client.generation_budget,
        "review_id": payload["review_id"],
        "workload_brief": payload["workload_brief"],
        "retrieval_query": payload["retrieval_query"],
        "rule_findings": [],
        "terraform_resources": payload.get("terraform_resources", {}),
        "preflight_fields": payload.get("preflight_fields", {}),
        "embedding_client": _EMBEDDING_CLIENT,
        "vectors_client": _VECTORS_CLIENT,
        "lexical_corpus_index": _LEXICAL_CORPUS_INDEX,
        "guardrails_client": _GUARDRAILS_CLIENT,
        "reasoning_client": reasoning_client,
        "max_tokens": min(_MAX_TOKENS, 4096),
        "corpus_version": payload.get("corpus_version", "unknown"),
        "deterministic_rule_version": payload.get("deterministic_rule_version"),
        "deep_mode": True,
        "parent_finding_id": payload["parent_finding_id"],
        "parent_finding": payload.get("parent_finding"),
    }
    try:
        result_state = _DEEPER_GRAPH.invoke(initial_state)
    except AdmissionDenied as exc:
        _log_refusal("graph", exc, payload, reasoning_client)
        return {"status": "admission_denied", "code": exc.code}
    except RequestBudgetExceeded as exc:
        _log_refusal("graph", exc, payload, reasoning_client)
        return _bounded_result(payload, exc.code)
    return {
        "status": "complete",
        "findings": result_state.get("reasoned_findings", []),
        "dropped_model_findings": result_state.get("dropped_model_findings", []),
        "unverified_findings": result_state.get("unverified_findings", []),
        "disproved_findings": result_state.get("disproved_findings", []),
        "model_output_counts": result_state.get("model_output_counts"),
        "model_findings_capped": result_state.get("model_findings_capped", 0),
        "retrieval_omitted_count": result_state.get("retrieval_omitted_count", 0),
    }


@app.entrypoint
def invoke(payload: dict[str, Any], context: Any) -> dict[str, Any]:
    """One review's PreflightGate -> Retrieve -> Reason pass, OR (when
    `payload["mode"] == "deeper"`) a scoped "go deeper" Retrieve ->
    Reason(deep) re-run for one finding — see _invoke_deeper. One
    AgentCore Runtime, one entrypoint, branching on `mode` rather than a
    second deployed runtime, since both paths need the same Bedrock
    model/IAM role and only differ in which graph they run.

    `payload` is whatever Step Functions' InvokeAgent task sends — per
    infra/modules/step-functions-lambda's ResultPath comment, this is the
    full prior state (review_id, workload_brief, baseline_answers,
    retrieval_query, rule_findings) JSON-serialized via States.JsonToString.

    Real failures (GuardrailBlocked from reason_node, FindingValidationError/
    ModelOutputTruncated/UnexpectedStopReason/ToolCallMissing from
    reason.py/clients) are deliberately left to propagate as real exceptions
    rather than caught and returned as an {"error": ...} dict. AgentCore
    surfaces an uncaught exception as a real runtime invocation error Step
    Functions can react to (Catch/Retry on the Task); a normally-RETURNED
    error dict would look like SUCCESS to Step Functions and silently proceed
    to Validate with no real findings. needs_clarification (preflight pausing
    for a required field) is the one legitimate non-exception "stop" outcome —
    a real, expected result, not a failure — so it's returned explicitly
    instead.

    Returns a SMALL, EXPLICIT JSON-serializable result — never the raw
    graph state, which carries boto3 client objects (not JSON-serializable)
    and the full retrieved_chunks list (Step Functions has a 256 KiB state
    size limit; nothing downstream of this entrypoint needs the raw
    chunks, only the findings they produced).
    """
    try:
        admission = authorize_payload(payload)
    except AdmissionDenied as exc:
        return {"status": "admission_denied", "code": exc.code}
    if payload.get("mode") == "deeper":
        return _invoke_deeper(payload)

    try:
        reasoning_client = _budget_client(payload, _REASONING_CLIENT)
    except AdmissionDenied as exc:
        return {"status": "admission_denied", "code": exc.code}

    initial_state: ReviewState = {
        "paid_scope_context": admission,
        "generation_budget": reasoning_client.generation_budget,
        "review_id": payload["review_id"],
        "workload_brief": payload["workload_brief"],
        "baseline_answers": payload.get("baseline_answers", {}),
        "retrieval_query": payload["retrieval_query"],
        "rule_findings": payload.get("rule_findings", []),
        "terraform_resources": payload.get("terraform_resources", {}),
        "embedding_client": _EMBEDDING_CLIENT,
        "vectors_client": _VECTORS_CLIENT,
        "lexical_corpus_index": _LEXICAL_CORPUS_INDEX,
        "guardrails_client": _GUARDRAILS_CLIENT,
        "reasoning_client": reasoning_client,
        "max_tokens": min(_MAX_TOKENS, 12288),
        "verification_enabled": reasoning_client.generation_budget.verification_enabled,
        "corpus_version": payload.get("corpus_version", "unknown"),
        "deterministic_rule_version": payload.get("deterministic_rule_version"),
    }

    # No checkpointer exists on this graph today, so LangGraph's own
    # thread_id isn't required for correctness — context.session_id (set
    # by the Step Functions RuntimeSessionId parameter) is available for
    # request correlation/logging if needed.
    try:
        result_state = _GRAPH.invoke(initial_state)
    except AdmissionDenied as exc:
        _log_refusal("graph", exc, payload, reasoning_client)
        return {"status": "admission_denied", "code": exc.code}
    except RequestBudgetExceeded as exc:
        _log_refusal("graph", exc, payload, reasoning_client)
        return _bounded_result(payload, exc.code)

    if result_state.get("needs_clarification"):
        return {
            "status": "needs_clarification",
            "needs_clarification": result_state["needs_clarification"],
            "preflight_fields": result_state.get("preflight_fields", {}),
        }

    return {
        "status": "complete",
        "findings": result_state.get("reasoned_findings", []),
        "dropped_model_findings": result_state.get("dropped_model_findings", []),
        "unverified_findings": result_state.get("unverified_findings", []),
        "disproved_findings": result_state.get("disproved_findings", []),
        "model_output_counts": result_state.get("model_output_counts"),
        "model_findings_capped": result_state.get("model_findings_capped", 0),
        "retrieval_omitted_count": result_state.get("retrieval_omitted_count", 0),
        # Returned on the success path too, so Finalize can persist
        "additional_verification": result_state.get("additional_verification"),
        # per-field preflight outcomes for a completed review.
        "preflight_fields": result_state.get("preflight_fields", {}),
        "defaults_version": result_state.get("defaults_version"),
    }


if __name__ == "__main__":
    app.run()
