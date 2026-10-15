---
title: "ADR 0033: Corrected Hugging Face Implementation Path"
type: decision
tags: [adr, project, work-project, archibrief]
created: "2026-09-03"
updated: "2026-09-03"
status: accepted
---

# ADR 0033: Corrected Hugging Face Implementation Path

**Status:** Accepted (2026-09-03) — **supersedes** ADR-0014's proposed
implementation path (the underlying goal itself stands)

## Context

Verified directly against AWS's Bedrock Custom Model Import documentation
and Meta's Llama Prompt Guard 2 model card: Custom Model Import supports
Mistral, Mixtral, Flan, Llama 2/3.x, GPTBigCode, Qwen2/2.5/3, and GPT-OSS
architectures only — **not** DeBERTa, Gemma, or DeepSeek. Llama Prompt
Guard 2 is mDeBERTa/DeBERTa-xsmall based, so it cannot be imported via
this path. ADR-0014's proposed implementation was factually broken.

## Decision

- Use **Bedrock Guardrails' prompt-attack detection** as the actual
  supported production control (replaces the Custom-Model-Import-based
  classifier in ADR-0022's layer 1).
- If Prompt Guard 2 specifically is wanted, run it separately in a
  constrained Lambda container or other isolated inference path as a
  **shadow/evaluation candidate**, not the production path, and only
  promote it if measured false-positive/false-negative rate, latency, and
  cost justify it on ArchiBrief's own adversarial test set.
- If Custom Model Import is still wanted, select an
  actually-supported architecture (Mistral, Llama, Qwen, etc.) for a real,
  useful, measured task — not forced through for a task it can't perform.
- Budget for Custom Model Import's real cost shape: five-minute billing
  windows, monthly model storage, and cold starts — scale-to-zero doesn't
  mean per-invocation pricing behaves like ordinary token-based inference.

## Consequences

- Preserves the original goal (real Hugging Face/Bedrock integration)
  while fixing the technical error.
- ADR-0022 (prompt-injection defense) updates layer 1 accordingly — see
  ADR-0038.

## Full reasoning

See an independent design review §"ADR-0014" and the direct AWS/
Hugging Face documentation verification performed 2026-09-03.
