"""AgentCore Runtime entrypoint for the PreflightGate -> Retrieve -> Reason
subworkflow (ADR-0028).

This is what infra/modules/agentcore-runtime deploys — the piece that
lets Step Functions' InvokeAgent task (infra/modules/step-functions-lambda)
call something real instead of a placeholder ARN. Everything before
(Ingest, RuleEngine) and after (Validate, Audit, Finalize) stays outside
this entrypoint entirely, as bounded Lambda work Step Functions
orchestrates directly (ADR-0028) — this file owns exactly the LangGraph
subworkflow and nothing else.

Standard AgentCore pattern (BedrockAgentCoreApp + @app.entrypoint),
confirmed against AWS's own docs 2026-09-16: the compiled graph and every
real AWS client it needs are built ONCE at import/module time, not
per-invocation, so a warm process reuses them across requests. AgentCore
does not promise reuse across cold starts, so nothing here assumes state
survives a cold start that wasn't explicitly rebuilt from these
module-level singletons.

UNVERIFIED, flagged deliberately (2026-09-16): no live example was found
combining LangGraph + AgentCore's ZIP/code_configuration deployment path +
native Terraform aws_bedrockagentcore_agent_runtime specifically. Prior art
exists for LangGraph-on-AgentCore via container deployment, and for
ZIP/code deployment via Terraform for non-LangGraph agents, but not this
exact combination. The entrypoint contract below (input/output shape,
exception-propagation choice) is a best-effort design against AWS's
documented AgentCore patterns, not confirmed against a real deployment.
"""

from __future__ import annotations

import os
from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from backend.agent.graph import ReviewState, compiled_graph
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

# This is the REAL production entrypoint — unlike validate_reason_node.py
# (a manual script that hardcodes its model ID with a large revert-comment
# because ADR-0006 pins Sonnet 5 but account access is still pending), this
# file must not hardcode a model string per the plan already recorded in
# [[project_archibrief_rag_progress]]: "when the real production invocation
# entrypoint gets built, don't hardcode a model string there either — wire
# it to an env var". Default still follows the same temporary Sonnet 4.6
# stand-in as every other real call site until Sonnet 5 access clears.
_MODEL_ID = os.environ.get("ARCHIBRIEF_REASONING_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
_MAX_TOKENS = int(os.environ.get("ARCHIBRIEF_REASONING_MAX_TOKENS", "8192"))

app = BedrockAgentCoreApp()

# Built once at import time, reused across a warm process — see module
# docstring. build_lexical_corpus_index_from_disk() reads backend/corpus/
# JSON data files that must ship inside the deployment artifact (flagged
# in infra/modules/agentcore-runtime's own packaging notes).
_GRAPH = compiled_graph()
_EMBEDDING_CLIENT = BedrockEmbeddingClient(region_name=_REGION)
_VECTORS_CLIENT = S3VectorsClient(
    bucket_name=_VECTOR_BUCKET_NAME, index_name=_VECTOR_INDEX_NAME, region_name=_REGION
)
_LEXICAL_CORPUS_INDEX = build_lexical_corpus_index_from_disk()
_GUARDRAILS_CLIENT = GuardrailsClient(
    guardrail_id=_GUARDRAIL_ID, guardrail_version=_GUARDRAIL_VERSION, region_name=_REGION
)
_REASONING_CLIENT = BedrockReasoningClient(model_id=_MODEL_ID, region_name=_REGION)


@app.entrypoint
def invoke(payload: dict[str, Any], context: Any) -> dict[str, Any]:
    """One review's PreflightGate -> Retrieve -> Reason pass.

    `payload` is whatever Step Functions' InvokeAgent task sends — per
    infra/modules/step-functions-lambda's ResultPath comment, this is the
    full prior state (review_id, workload_brief, baseline_answers,
    retrieval_query, rule_findings) JSON-serialized via States.JsonToString.

    Real failures (GuardrailBlocked from reason_node, FindingValidationError/
    ModelOutputTruncated/UnexpectedStopReason/ToolCallMissing from
    reason.py/clients) are deliberately left to propagate as real
    exceptions rather than caught and returned as an {"error": ...} dict —
    per this task's own directive: AgentCore surfaces an uncaught exception
    as a real runtime invocation error Step Functions can react to (Catch/
    Retry on the Task); a normally-RETURNED error dict would look like
    SUCCESS to Step Functions and silently proceed to Validate with no
    real findings. needs_clarification (preflight pausing for a required
    field) is the one legitimate non-exception "stop" outcome — a real,
    expected result, not a failure — so it's returned explicitly instead.

    Returns a SMALL, EXPLICIT JSON-serializable result — never the raw
    graph state, which carries boto3 client objects (not JSON-serializable)
    and the full retrieved_chunks list (Step Functions has a 256 KiB state
    size limit; nothing downstream of this entrypoint needs the raw
    chunks, only the findings they produced).
    """
    initial_state: ReviewState = {
        "review_id": payload["review_id"],
        "workload_brief": payload["workload_brief"],
        "baseline_answers": payload.get("baseline_answers", {}),
        "retrieval_query": payload["retrieval_query"],
        "rule_findings": payload.get("rule_findings", []),
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
    # request correlation/logging if needed, deliberately not wired into
    # a checkpointer here since adding one is separate, unstarted scope.
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
    }


if __name__ == "__main__":
    app.run()
