"""LangGraph graph wiring for the ArchiBrief review subworkflow.

Owns exactly the PreflightGate -> Retrieve -> Reason subworkflow
(ADR-0028) inside AgentCore Runtime. Everything before (Ingest) and after
(Validate, Audit, Finalize) is bounded Lambda work orchestrated by the
outer Step Functions state machine — not part of this graph.

State is a plain dict passed and merged between nodes (LangGraph's
StateGraph with a TypedDict schema), matching System-Design's "object
identifiers pass between stages, not full payloads" — the dict here holds
S3/DynamoDB references and small scalars, not full repositories/reports.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from backend.agent.nodes.preflight import preflight_node
from backend.agent.nodes.reason import reason_node
from backend.agent.nodes.retrieve import retrieve_node
from backend.shared.clients import (
    BedrockEmbeddingClient,
    BedrockReasoningClient,
    GuardrailsClient,
    S3VectorsClient,
)


class ReviewState(TypedDict, total=False):
    review_id: str
    workload_brief: str
    baseline_answers: dict[str, str]
    preflight_fields: dict[str, Any]
    needs_clarification: list[str]
    status: str
    # preflight_node also sets this (DEFAULT_VERSION) but it wasn't
    # declared here until 2026-10-01 — same silent-drop failure mode as
    # every other field in this comment block. Needed on the SUCCESS path
    # now too (not just needs_clarification): finalize.handler uses it to
    # tag every persisted baseline answer with the defaults policy version
    # that produced it.
    defaults_version: str
    retrieval_query: str
    # LangGraph's StateGraph only tracks channels declared on this
    # TypedDict — a key a node reads/writes that isn't declared here gets
    # silently dropped between nodes even though preflight_node's own
    # `**state` passthrough looks like it should carry it forward.
    # Confirmed directly (2026-09-15): invoking the compiled graph with
    # embedding_client/vectors_client in the initial state raised
    # KeyError inside retrieve_node, since preflight->retrieve had already
    # dropped them. These three must stay declared here for retrieve_node
    # to actually receive real client instances + the lexical index when
    # invoked through the compiled graph, not just when called directly.
    embedding_client: BedrockEmbeddingClient
    vectors_client: S3VectorsClient
    lexical_corpus_index: dict[str, list[dict]]
    retrieved_chunks: list[dict]
    rule_findings: list[dict]
    # RuleEngine's resource_summary (#15b); undeclared, it would be dropped
    # before reason_node like the fields above.
    terraform_resources: dict[str, Any]
    # Same silent-drop failure mode as the three fields above, confirmed
    # by the same mechanism — reason_node reads these two off state but
    # LangGraph never carries an undeclared key past a node boundary.
    guardrails_client: GuardrailsClient
    reasoning_client: BedrockReasoningClient
    # A THIRD instance of the exact same silent-drop bug, found while
    # scoping AgentCore Runtime deployment (2026-09-16): reason_node also
    # reads state.get("max_tokens", 4096), state.get("corpus_version",
    # "unknown"), and state.get("deterministic_rule_version") — none of
    # which were declared here. Any caller (including the real AgentCore
    # entrypoint, backend/agent/runtime_entrypoint.py) that set these on
    # the initial state before invoking the compiled graph would have had
    # them silently dropped before reaching reason_node, silently falling
    # back to the hardcoded defaults every time.
    max_tokens: int
    corpus_version: str
    deterministic_rule_version: str | None
    reasoned_findings: list[dict]
    # Model findings excluded by citation/shape verification (reason_node).
    dropped_model_findings: list[str]
    # "Go deeper" only (build_deeper_graph below) — same silent-drop
    # failure mode as every other field in this TypedDict, so both must
    # be declared here even though build_graph()'s own path never sets
    # them. reason_node reads deep_mode to pick the deep-mode system
    # prompt variant and stamp depth_level="deep"; parent_finding_id is
    # carried through to the resulting Finding so it's a versioned child
    # of the original, never a disconnected result (ADR-0039).
    deep_mode: bool
    parent_finding_id: str | None


def route_after_preflight(state: ReviewState) -> str:
    return END if state.get("needs_clarification") else "retrieve"


def build_graph() -> StateGraph:
    graph = StateGraph(ReviewState)
    graph.add_node("preflight", preflight_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("reason", reason_node)

    graph.set_entry_point("preflight")
    graph.add_conditional_edges(
        "preflight", route_after_preflight, {"retrieve": "retrieve", END: END}
    )
    graph.add_edge("retrieve", "reason")
    graph.add_edge("reason", END)

    return graph


def compiled_graph():
    return build_graph().compile()


# "Go deeper" (ADR-0023/ADR-0039, 2026-10-01): scoped per-finding re-run,
# Retrieve -> Reason only — never re-enters PreflightGate (baseline
# answers were already settled on the original run; re-asking per
# ADR-0031 would be a disconnected second review, not a versioned child
# of the first) and never re-runs Ingest/RuleEngine/Validate/Audit/
# Finalize (System-Design: "does not re-run the full pipeline" — those
# stay bounded Lambda work the deeper_review Lambda itself does directly,
# not duplicated into this graph). Same preflight.py/retrieve.py/
# reason.py node functions as build_graph() — no forked copy of the real
# logic, just a different, shorter wiring of the same nodes.
def build_deeper_graph() -> StateGraph:
    graph = StateGraph(ReviewState)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("reason", reason_node)

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "reason")
    graph.add_edge("reason", END)

    return graph


def compiled_deeper_graph():
    return build_deeper_graph().compile()
