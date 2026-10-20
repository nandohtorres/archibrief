# ADR 0009: Backend Language — Python

**Status:** Accepted (2026-09-02) — **amended by
[ADR-0042](0042-minor-amendments-batch.md)** (2026-09-03): Python
choice stands; adds a supported Lambda/AgentCore runtime, strict type
checking, and one schema definition for the typed evidence ledger
(already reflected in the coding conventions).

## Context

Choice between Python (dominant in RAG/LLM tooling, pairs naturally with
Lambda) and Node/TypeScript (closer to an existing React background).

## Decision

**Python.** The project owner's stated preference, and the dominant
language of the RAG/LLM/LangGraph ecosystem.

## Consequences

- Frontend framework/language choice remains a separate, open decision —
  not implied by this one.
