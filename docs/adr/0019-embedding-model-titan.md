# ADR 0019: Embedding Model — Titan V2

**Status:** Accepted (2026-09-03) — **framing superseded by
[ADR-0035](0035-titan-baseline-not-cost-locked.md)** (2026-09-03):
Titan stays the working choice, but as a baseline pending evaluation, not
a cost-justified final answer; the reversibility claim was also
corrected.

## Context

Both Titan V2 and Cohere Embed v3 are available directly through Bedrock
(neither breaks the AWS-native story, ADR-0006). Titan V2 costs
$0.02/1M tokens; Cohere costs $0.10/1M tokens (5x). Research found Cohere
scores better on RAG-specific retrieval benchmarks — **this is a
cost-vs-quality tradeoff, not a case where the data picks Titan as
objectively better.**

## Decision

**Titan V2**, chosen for cost given the $50/mo budget target (ADR-0024).
Explicitly a swappable choice, not a one-way door — both models live in
Bedrock, so switching later requires only a config change, not an
architecture change.

## Consequences

- Retrieval quality may be a notch below what Cohere would deliver —
  worth revisiting if evaluation (ADR-0023) surfaces retrieval-quality
  problems specifically traceable to the embedding model.
