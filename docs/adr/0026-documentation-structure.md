# ADR 0026: Documentation Structure — Journal, Spec, Build Plan, ADRs

**Status:** Accepted (2026-09-03)

## Context

As decisions accumulated, the project's decision log (a single growing
narrative) and its spec (a distilled summary of the same decisions)
started duplicating content and risked drifting out of sync — every new
decision required updating both by hand. The goal was clean file
separation that shows the design thinking publicly, while still keeping
one comprehensive narrative record.

Considered: (1) adopt Architecture Decision Records + keep Spec/Build
Plan as current-state-only docs; (2) keep the status quo (one growing
log + a duplicate Spec); (3) drop the narrative log entirely, Spec/Build
Plan only. Ranked in that order — (1) best (fixes duplication at the
root, matches a real, GitHub-recognizable standard: Michael Nygard's 2011
ADR convention, used by AWS/GitHub/Red Hat); (2) works but the drift risk
only grows; (3) rejected outright — throws away the "why," which the
project deliberately preserves.

## Decision

Four-document structure, verified real/standard before adopting (ADR
practice confirmed via
[joelparkerhenderson/architecture-decision-record](https://github.com/joelparkerhenderson/architecture-decision-record)):

- **Journal** — full narrative/decision log, kept so the comprehensive
  story lives in one place.
- **Spec** — distilled current-state summary, no debate history, links to
  ADRs instead of restating reasoning.
- **ADRs** — one short, atomic, immutable-once-accepted file per real
  decision (this folder), portable into the code repo's `docs/adr/`.
- **Build Plan** — ordered implementation steps, referencing the Spec
  rather than restating it.

The journal, spec, and build plan are private working notes; only the
ADRs are published with the code.

Duplication between the Journal and the ADRs is explicitly accepted, not
treated as a problem — they serve different readers (a comprehensive
private reference vs. atomic public records), so pointers between them
are sufficient; no requirement to eliminate all overlap.

## Consequences

- Renaming the internal document slots after the product name was
  considered and declined (2026-09-03): stable slot names mean a future
  product rename (this is already the second name) never requires a
  risky mass rename across cross-linked notes.
- Going forward: a new architectural decision gets a new ADR at the time
  it's made, not batched later.
