---
title: "ADR 0008: Agent Framework — LangGraph on Bedrock AgentCore"
type: decision
tags: [adr, project, work-project, archibrief]
created: "2026-09-02"
updated: "2026-09-03"
status: accepted
---

# ADR 0008: Agent Framework — LangGraph on Bedrock AgentCore

**Status:** Accepted (2026-09-02) — **extended by
[ADR-0028](Work-Project-ADR-0028-Orchestration-Ownership-Boundary.md)**
(2026-09-03): the LangGraph-on-AgentCore choice stands; ADR-0028 defines
what it owns (the one reasoning/retrieval subworkflow) versus Step
Functions/Lambda, closing a real duplication risk Codex flagged.

## Context

Weighed simple custom orchestration (Step Functions + direct LLM calls,
no framework) against a named agent framework, given the resume value of
using a framework worth naming in an interview. A 2026 job-market study
found LangGraph has the second-highest hiring footprint among agent
frameworks despite fewer GitHub stars than competitors, and all major
frameworks sit in the same $185-190k median-salary band.

## Decision

**LangGraph running on Bedrock AgentCore.** AgentCore (GA Oct 2025) is
AWS's own framework-agnostic agent runtime with native LangGraph memory
integration, so the pairing keeps the AWS-native story while adding a
real, named framework skill. Graph-based state management fits the
"deterministic rules + RAG/LLM synthesis" pipeline shape.

## Consequences

- **Scope tradeoff, explicitly flagged:** more to build/learn than the
  original "simple custom orchestration" assumption.
- Directly supports ADR-0012 (baseline pre-flight gate as a graph node).

## Full reasoning

See the project decision log §"W1-W4 stack research findings" and
Research Work Agent Framework.
