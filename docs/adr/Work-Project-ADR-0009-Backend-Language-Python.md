---
title: "ADR 0009: Backend Language — Python"
type: decision
tags: [adr, project, work-project, archibrief]
created: "2026-09-02"
updated: "2026-09-03"
status: accepted
---

# ADR 0009: Backend Language — Python

**Status:** Accepted (2026-09-02) — **amended by
[ADR-0042](Work-Project-ADR-0042-Minor-Amendments-Batch.md)** (2026-09-03): Python
choice stands; adds a supported Lambda/AgentCore runtime, strict type
checking, and one schema definition for the typed evidence ledger
(already reflected in the coding conventions).

## Context

Choice between Python (dominant in RAG/LLM tooling, pairs naturally with
Lambda) and Node/TypeScript (consistent with Fernando's existing
React/PHP background).

## Decision

**Python.** Fernando's own stated preference, consistent with the
RAG/LLM/LangGraph ecosystem's dominant language.

## Consequences

- Frontend framework/language choice remains a separate, open decision —
  not implied by this one.

## Full reasoning

See the project decision log §"Open questions."
