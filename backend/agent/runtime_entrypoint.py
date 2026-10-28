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

import os
from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from backend.agent.graph import ReviewState, compiled_deeper_graph, compiled_graph
from backend.corpus.lexical_index import build_lexical_corpus_index_from_disk
from backend.shared.clients import (
    BedrockEmbeddingClient,
    BedrockReasoningClient,
    GuardrailsClient,
    S3VectorsClient,
)

_REGION = os.environ.get("AWS_REGION", "us-east-1")
_VECTOR_BUCKET_NAME = os.environ.get("ARCHIBRIEF_VECTOR_BUCKET", "archibrief-dev-kb")
_VECTOR_INDEX_NAME = os.environ.get("ARCHIBRIEF_VECTOR_INDEX", "archibrief-dev-kb-index")
_GUARDRAIL_ID = os.environ.get("ARCHIBRIEF_GUARDRAIL_ID", "")
_GUARDRAIL_VERSION = os.environ.get("ARCHIBRIEF_GUARDRAIL_VERSION", "1")

# The model ID comes from an env var so it can change without a code
# change; the default matches the other call sites.
_MODEL_ID = os.environ.get("ARCHIBRIEF_REASONING_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
_MAX_TOKENS = int(os.environ.get("ARCHIBRIEF_REASONING_MAX_TOKENS", "8192"))

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
    bucket_name=_VECTOR_BUCKET_NAME, index_name=_VECTOR_INDEX_NAME, region_name=_REGION
)
_LEXICAL_CORPUS_INDEX = build_lexical_corpus_index_from_disk()
_GUARDRAILS_CLIENT = GuardrailsClient(
    guardrail_id=_GUARDRAIL_ID,
    guardrail_version=_GUARDRAIL_VERSION,
    region_name=_REGION,
    no_retries=True,
)
# The reasoning call streams. The read timeout is the longest wait for the
# next chunk: a stalled call fails after it, while a long review that keeps
# writing does not (a 240 s wait for the whole response timed out on a
# large review, 2026-10-28). The deadline bounds the whole call; with
# retrieval and one last idle wait it stays below the 600 s the review
# worker waits for this runtime, so a slow call ends here first.
_REASONING_READ_TIMEOUT_SECONDS = float(
    os.environ.get("ARCHIBRIEF_REASONING_READ_TIMEOUT_SECONDS", "90")
)
_REASONING_DEADLINE_SECONDS = float(os.environ.get("ARCHIBRIEF_REASONING_DEADLINE_SECONDS", "420"))
_REASONING_CLIENT = BedrockReasoningClient(
    model_id=_MODEL_ID,
    region_name=_REGION,
    no_retries=True,
    read_timeout_seconds=_REASONING_READ_TIMEOUT_SECONDS,
    stream_deadline_seconds=_REASONING_DEADLINE_SECONDS,
)
# "Go deeper" re-reviews one finding, so its output is short, and its
# worker waits only 300 s for this runtime: a tighter deadline keeps the
# whole call (plus one last idle wait) inside that.
_DEEPER_REASONING_DEADLINE_SECONDS = float(
    os.environ.get("ARCHIBRIEF_DEEPER_REASONING_DEADLINE_SECONDS", "180")
)
_DEEPER_REASONING_CLIENT = BedrockReasoningClient(
    model_id=_MODEL_ID,
    region_name=_REGION,
    no_retries=True,
    read_timeout_seconds=_REASONING_READ_TIMEOUT_SECONDS,
    stream_deadline_seconds=_DEEPER_REASONING_DEADLINE_SECONDS,
)


def _invoke_deeper(payload: dict[str, Any]) -> dict[str, Any]:
    """Go-deeper pass: Retrieve -> Reason(deep) only, scoped to one
    finding. Called by deeper_review.handler (behind
    POST /reviews/{reviewId}/findings/{findingId}/deeper), never by the
    outer Step Functions state machine. PreflightGate is not rerun;
    the original settled requirements and resource observations are reused.
    """
    initial_state: ReviewState = {
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
        "reasoning_client": _DEEPER_REASONING_CLIENT,
        "max_tokens": payload.get("max_tokens", _MAX_TOKENS),
        "corpus_version": payload.get("corpus_version", "unknown"),
        "deterministic_rule_version": payload.get("deterministic_rule_version"),
        "deep_mode": True,
        "parent_finding_id": payload["parent_finding_id"],
        "parent_finding": payload.get("parent_finding"),
    }
    result_state = _DEEPER_GRAPH.invoke(initial_state)
    return {
        "status": "complete",
        "findings": result_state.get("reasoned_findings", []),
        "dropped_model_findings": result_state.get("dropped_model_findings", []),
        "model_output_counts": result_state.get("model_output_counts"),
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
    ModelOutputTruncated/UnexpectedStopReason/ToolCallMissing/
    ReasoningDeadlineExceeded from
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
    if payload.get("mode") == "deeper":
        return _invoke_deeper(payload)

    initial_state: ReviewState = {
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
        "reasoning_client": _REASONING_CLIENT,
        "max_tokens": payload.get("max_tokens", _MAX_TOKENS),
        "corpus_version": payload.get("corpus_version", "unknown"),
        "deterministic_rule_version": payload.get("deterministic_rule_version"),
    }

    # No checkpointer exists on this graph today, so LangGraph's own
    # thread_id isn't required for correctness — context.session_id (set
    # by the Step Functions RuntimeSessionId parameter) is available for
    # request correlation/logging if needed.
    result_state = _GRAPH.invoke(initial_state)

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
        "model_output_counts": result_state.get("model_output_counts"),
        # Returned on the success path too, so Finalize can persist
        # per-field preflight outcomes for a completed review.
        "preflight_fields": result_state.get("preflight_fields", {}),
        "defaults_version": result_state.get("defaults_version"),
    }


if __name__ == "__main__":
    app.run()
