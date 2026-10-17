# ADR 0013: UI Build Sequencing

**Status:** Accepted (2026-09-02) — **milestone framing superseded by
[ADR-0032](0032-ui-vertical-slice-milestones.md)** (2026-09-03):
the early/parallel UI-build intent stands, but the "~60-70% visual
polish" percentage was replaced with concrete, checkable vertical-slice
milestones.

## Context

The goal was a full, high-quality UI as early as possible — initially in
apparent tension with the locked v1 decision that output starts as a
structured HTML/JSON evidence ledger before any polished UI layer
(ADR-0002/v1 scope).

## Decision

UI work starts early, running roughly in parallel with backend work —
target ~60-70% of visual/aesthetic completeness built early, remaining
polish (sizing, fine detail) in later phases. Reason: using the UI
throughout the build makes the developer its first tester and catches
UX issues early, not just at the end.

This does not expand v1's scope — the evidence-ledger data model stays
the foundation; the UI is what renders it. Practical effect: the ledger's
data contract/schema needs to stabilize earlier than originally implied
by the 5-phase roadmap.

## Consequences

- Frontend/backend phases run closer to parallel, not strictly
  sequential.
