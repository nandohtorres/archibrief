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
    # Same silent-drop failure mode as the three fields above, confirmed
    # by the same mechanism — reason_node reads these two off state but
    # LangGraph never carries an undeclared key past a node boundary.
    guardrails_client: GuardrailsClient
    reasoning_client: BedrockReasoningClient
    reasoned_findings: list[dict]


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
