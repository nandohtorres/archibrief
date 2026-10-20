# ADR 0039: Base-Report Field Completeness and Versioned Snapshots

**Status:** Accepted (2026-09-03) — **extends** ADR-0023, doesn't reverse
the lightweight-first-pass default

## Context

A design review flagged a real risk in ADR-0023's "brief explanation +
citation" lightweight default: read loosely, it could be taken to mean
the base report omits required fields (risk/impact, confidence inputs,
alternatives, framework mapping) that ADR-0002 already requires on every
finding. Separately, without versioning, a
"go deeper" request run after the corpus or model changes could silently
contradict the original finding.

## Decision

- The base (lightweight) report must still contain **every required
  typed field** — finding, evidence, confidence inputs, risk/impact,
  recommendation, applicable framework mapping — even when the prose is
  brief. "Go deeper" expands analysis depth; it does not backfill fields
  the original result lacked.
- Persist the original model ID, prompt version, corpus version,
  retrieved chunks, and deterministic-rule version with every result. A
  "go deeper" request is a **versioned child** of that snapshot, not a
  fresh, disconnected re-run — protects reproducibility if the corpus or
  model changes between the original review and a later deep-dive.
- Measure which findings users actually expand, abandonment rate,
  latency, and cost before ever changing the lightweight default.

## Consequences

- The `Findings` data model includes snapshot/version fields.
