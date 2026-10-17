# ADR 0023: Evaluation-Depth Strategy

**Status:** Accepted (2026-09-03), with an explicit planned revisit —
**extended by [ADR-0039](0039-base-report-field-completeness.md)**
(2026-09-03): the lightweight-first-pass default stands; ADR-0039
clarifies that "lightweight" constrains prose depth only (every required
typed field is still populated) and adds versioned snapshots so "go
deeper" can't silently contradict the original result.

## Context

Real UX-vs-cost-vs-latency tradeoff, previously flagged as explicitly
undecided: full-depth evaluation on every finding by default, vs. a
lighter first-pass with on-demand deeper evaluation per finding.

## Decision

**Lightweight first pass by default**: every finding gets a brief
explanation + citation. A user-triggered "go deeper" action per finding
runs additional retrieval/evaluation only on request. **Explicitly
planned to be revisited** once a working version exists and real UX
signal is available — it may switch to full-depth-by-default later
depending on how the lightweight version actually feels to use.

## Consequences

- Cheaper and faster on average for v1.
- This decision is intentionally provisional, not a permanent
  architectural commitment — flag before assuming it's final in any
  future planning.
