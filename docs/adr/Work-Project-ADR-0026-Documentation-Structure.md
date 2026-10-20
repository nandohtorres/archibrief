---
title: "ADR 0026: Documentation Structure — Journal, Spec, Build Plan, ADRs"
type: decision
tags: [adr, project, work-project, archibrief, meta]
created: "2026-09-03"
updated: "2026-09-03"
status: accepted
---

# ADR 0026: Documentation Structure — Journal, Spec, Build Plan, ADRs

**Status:** Accepted (2026-09-03)

## Context

As decisions accumulated, the project decision log (a single growing
narrative/decision-log) and the project spec (a distilled summary of
the same decisions) started duplicating content and risked drifting out
of sync — every new decision required updating both by hand. Fernando
wanted good file separation for public-repo purposes ("show good thinking
and proper design system") while also keeping a comprehensive narrative
file he personally enjoys having.

Considered: (1) adopt Architecture Decision Records + keep Spec/Build
Plan as current-state-only docs; (2) keep the status quo (one growing
log + a duplicate Spec); (3) drop the narrative log entirely, Spec/Build
Plan only. Ranked in that order — (1) best (fixes duplication at the
root, matches a real, GitHub-recognizable standard: Michael Nygard's 2011
ADR convention, used by AWS/GitHub/Red Hat); (2) works but the drift risk
only grows; (3) rejected outright — throws away the "why," violating the
standing decision-context-preservation rule.

## Decision

Four-file structure per project, verified real/standard before adopting
(ADR practice confirmed via
[joelparkerhenderson/architecture-decision-record](https://github.com/joelparkerhenderson/architecture-decision-record)):

- **`Work-Project.md`** — full narrative/decision-log, unchanged role,
  kept because Fernando explicitly values having the comprehensive story
  in one place.
- **`Work-Project-Spec.md`** — distilled current-state summary, no debate
  history, links to ADRs instead of restating reasoning.
- **`Work-Project-ADR/`** — one short, atomic, immutable-once-accepted
  file per real decision (this folder). Portable into the eventual code
  repo's `docs/adr/` for public-repo credibility.
- **`Work-Project-Build-Plan.md`** — ordered implementation steps,
  referencing the Spec rather than restating it.

Duplication between the Journal and the ADRs is explicitly accepted, not
treated as a problem — different readers (Fernando's own comprehensive
reference vs. atomic public records), so trail-pointers between them are
sufficient; no requirement to eliminate all overlap.

## Consequences

- Renaming `Work-Project.md` → `ArchiBrief.md` etc. was separately
  considered and explicitly declined (2026-09-03) — kept as a stable
  internal slot name so a future product rename (this is already the
  second name) never requires a risky mass-rename across the vault's
  wikilink graph.
- Going forward: a new architectural decision gets a new ADR at the time
  it's made, not batched later.

## Full reasoning

See conversation 2026-09-02/09-03 on file organization (also ADR-0015 for
the related public-repo/no-dummy-repo decision).
