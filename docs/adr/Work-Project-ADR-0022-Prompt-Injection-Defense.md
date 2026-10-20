---
title: "ADR 0022: Prompt-Injection Defense Architecture"
type: decision
tags: [adr, project, work-project, archibrief, security]
created: "2026-09-03"
updated: "2026-09-03"
status: accepted
---

# ADR 0022: Prompt-Injection Defense Architecture

**Status:** Accepted (2026-09-03) — **extended by
[ADR-0038](Work-Project-ADR-0038-Prompt-Injection-Architectural-Boundaries.md)**
(2026-09-03): the five original controls stand (layer 1's implementation
corrected to Bedrock Guardrails by
[ADR-0033](Work-Project-ADR-0033-Hugging-Face-Path-Corrected.md)); ADR-0038 adds
architectural controls that don't depend on the model behaving correctly.

## Context

Users submit their own Terraform + brief text, which gets fed to an LLM
— a real attack surface. Full 2026 enterprise defense-in-depth stacks run
~6 layers (input classifier, structured separation, dual-LLM patterns,
typed tool calls, output validation, audit logging), which is more than
this project's scope needs. Separately, Fernando raised a related but
distinct concern: protecting against cost/billing abuse ("denial of
wallet") — largely covered by ADR-0011's rate limiting, but a malicious
input could specifically try to trigger unusually expensive processing.

## Decision

Scoped-down stack, four layers plus one cost-specific addition:

1. **Input classifier pass** on submitted content (could use an open
   classifier like Llama Prompt Guard 2 via the Bedrock Custom Model
   Import path from ADR-0014).
2. **Structured separation** of system prompt vs. user-submitted content
   (XML/JSON tags), so the model can distinguish instructions from data.
3. **Output validation** against the typed-finding schema (ADR-0002) —
   rejects/flags output that doesn't conform.
4. **Audit logging** — a successful or attempted injection produces a
   traceable log entry, not just a silent pass/fail.
5. **Per-request hard caps** (max tokens per LLM call, max retrieval
   calls per review) — the direct guard against injection-driven
   cost/denial-of-wallet abuse, complementing ADR-0011.

## Consequences

- Deliberately not the full 6-layer enterprise stack (dual-LLM
  patterns, typed MCP tool calls) — could be added later if real abuse
  patterns emerge.
- Covers **W5** (threat modeling + prompt-injection defenses) from
  the research task list.

## Full reasoning

See `AI-Drafts/Claude/work-project-stack-planning-qa.md` §"Round 2,"
question 7.
