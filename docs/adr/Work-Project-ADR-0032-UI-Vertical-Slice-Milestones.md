---
title: "ADR 0032: UI Vertical-Slice Milestones"
type: decision
tags: [adr, project, work-project, archibrief]
created: "2026-09-03"
updated: "2026-09-03"
status: accepted
---

# ADR 0032: UI Vertical-Slice Milestones

**Status:** Accepted (2026-09-03) — **extends** ADR-0013, doesn't reverse
the early-UI-work intent

## Context

Codex flagged that "~60-70% visual polish built early" (ADR-0013) is not
a testable/buildable milestone — it's a feeling, not a checkpoint.

## Decision

Replace the percentage with concrete, buildable milestones: an early
vertical slice containing submission, preflight interaction, progress
display, one complete typed finding with citation display, failure/empty
states, and the responsive shell. Use contract-generated fixtures (from
the system design notes' data models) while the backend is
incomplete. Defer decorative refinement and screens without a working
data contract behind them.

## Consequences

- Same underlying goal as ADR-0013 (Fernando as his own first UX tester,
  early) — now expressed as something the build plan can
  actually check off.

## Full reasoning

See an independent design review §"ADR-0013."
