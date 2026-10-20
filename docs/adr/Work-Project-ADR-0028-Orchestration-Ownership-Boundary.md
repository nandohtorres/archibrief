---
title: "ADR 0028: Orchestration Ownership Boundary"
type: decision
tags: [adr, project, work-project, archibrief]
created: "2026-09-03"
updated: "2026-09-03"
status: accepted
---

# ADR 0028: Orchestration Ownership Boundary

**Status:** Accepted (2026-09-03) — **extends** ADR-0005/ADR-0008,
resolves an ambiguity, doesn't reverse either

## Context

Codex's review flagged that Step Functions, LangGraph, and AgentCore
appeared to each own the workflow/preflight loop, with no single defined
boundary — a real risk of recreating the same discovery/retrieval/retry
graph in two places. Lambda also caps a normal invocation at 15 minutes,
relevant to where long-running work should live.

## Decision

- **Step Functions (Standard):** owns the durable outer job lifecycle
  only — accept, validate, persist input, run deterministic analysis,
  invoke one agent stage, validate/persist the result, publish status.
- **Lambda:** bounded, stateless deterministic functions (archive
  validation, HCL parsing, policy evaluation, result validation).
- **AgentCore Runtime + LangGraph:** the one reasoning/retrieval
  subworkflow, including the preflight branch if LangGraph genuinely owns
  it — not duplicated in Step Functions.
- Pass object identifiers (S3/DynamoDB references) between stages, not
  full repositories/reports through orchestration payloads.
- Do not add AgentCore Memory just because it exists — v1 is a bounded
  review with one preflight gate, not a long-running conversational
  assistant. Persist job state and the evidence ledger in DynamoDB/S3.

## Consequences

- Updates the system design notes' pipeline diagram — node
  ownership now explicit rather than implied.
- Keeps LangGraph (ADR-0008) in a real, bounded role without expanding the
  product around the framework.

## Full reasoning

See an independent design review §"ADR-0005," §"ADR-0008."
