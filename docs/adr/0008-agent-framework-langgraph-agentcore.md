# ADR 0008: Agent Framework — LangGraph on Bedrock AgentCore

**Status:** Accepted (2026-09-02) — **extended by
[ADR-0028](0028-orchestration-ownership-boundary.md)**
(2026-09-03): the LangGraph-on-AgentCore choice stands; ADR-0028 defines
what it owns (the one reasoning/retrieval subworkflow) versus Step
Functions/Lambda, closing a real duplication risk a design review flagged.

## Context

Weighed simple custom orchestration (Step Functions + direct LLM calls,
no framework) against an established agent framework. A framework brings
explicit graph-based state, checkpointing, and a well-documented model of
nodes and edges, at the cost of a dependency; LangGraph is among the most
widely adopted options.

## Decision

**LangGraph running on Bedrock AgentCore.** AgentCore (GA Oct 2025) is
AWS's own framework-agnostic agent runtime with native LangGraph memory
integration, so the pairing stays AWS-native while using a standard
framework rather than bespoke orchestration. Graph-based state management fits the
"deterministic rules + RAG/LLM synthesis" pipeline shape.

## Consequences

- **Scope tradeoff, explicitly flagged:** more to build/learn than the
  original "simple custom orchestration" assumption.
- Directly supports ADR-0012 (baseline pre-flight gate as a graph node).
