# ADR 0012: Agentic Complexity — Baseline Pre-Flight Gate

**Status:** Accepted (2026-09-02) — **missing-data default superseded by
[ADR-0031](0031-per-field-missing-data-policy.md)** (2026-09-03):
the pre-flight gate itself stands, but the blanket "assume the negative"
rule was replaced with a per-field policy.

## Context

Needed to decide how much "agentic" back-and-forth v1 has, given the
already-locked review-mode-first scope (ADR-0002).

## Decision

Before a review request runs, the tool checks a defined baseline set of
required workload-brief data points (regulatory/data-residency status,
expected traffic/scale, availability/criticality needs). If missing, it
asks the user. If unanswered, it proceeds using an explicit "assume the
negative" conservative default, and tags every finding that depends on
that default as `assumption` (per ADR-0002's typed-finding system). No
open-ended multi-turn chat/refinement loop after the report is generated.

## Consequences

- Bounded to one pre-flight gate — keeps build scope disciplined while
  still being genuinely agentic (the tool decides what's missing and
  either asks or degrades gracefully).
- Maps directly onto LangGraph's graph-node model (ADR-0008).
