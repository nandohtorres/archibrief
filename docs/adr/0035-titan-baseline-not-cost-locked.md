# ADR 0035: Titan V2 as Baseline Candidate, Not Cost-Locked Winner

**Status:** Accepted (2026-09-03) — **supersedes** ADR-0019's framing and
reversibility claim; the working choice (Titan V2, for now) is unchanged

## Context

A design review noted that at this corpus's small scale, the $0.02 vs.
$0.10-per-million-token difference between Titan and Cohere is unlikely
to materially affect a $50/month budget — the original cost justification
overweighted a small absolute difference. The review also corrected the
"swappable, config-only" claim: changing embedding models requires
re-embedding the full corpus, and Titan V2 supports 1,024/512/256-
dimensional output — if the dimension changes, S3 Vectors requires a new
index, since dimension is immutable after creation (verified against
AWS's own documentation).

Decided 2026-09-03: defer the formal Titan-vs-Cohere evaluation rather than build a dedicated eval harness now — reuse the
retrieval evaluation set that ADR-0036 (chunking) already requires,
rather than building two harnesses.

## Decision

**Titan V2 stays the working baseline for now** — but explicitly as a
baseline candidate pending evaluation, not a cost-justified final answer.
When the retrieval evaluation set exists (per ADR-0036), run Titan vs.
Cohere on the same frozen corpus/questions, measuring recall@k/nDCG,
citation-support rate, downstream answer correctness, latency, and total
cost. Titan remains the default only if it meets the quality bar;
otherwise switch to Cohere. Implement versioned blue/green indexes so a
model/dimension change can be evaluated and promoted without breaking the
live index.

## Consequences

- No immediate work required — this changes language/expectations, not
  the current implementation plan.
- Explicitly deferred, not decided — flag before treating Titan as
  final in any build-plan step downstream.
