---
title: "ADR 0031: Per-Field Missing-Data Policy"
type: decision
tags: [adr, project, work-project, archibrief]
created: "2026-09-03"
updated: "2026-09-03"
status: accepted
---

# ADR 0031: Per-Field Missing-Data Policy

**Status:** Accepted (2026-09-03) — **supersedes** ADR-0012's single
blanket "assume the negative" rule

## Context

Codex flagged that ADR-0012's blanket "assume the negative" default is
ambiguous and can be actively misleading — "no regulatory requirement" is
not a safe conservative assumption when the user simply doesn't know, and
an invented traffic/availability number can make a finding look more
certain than its actual evidence.

## Decision

Replace the single blanket default with a **per-field policy**, evaluated
per baseline data point at the PreflightGate node:

- **Cannot safely infer:** mark `unknown`/`not-observable`; state which
  conclusions can't be assessed; never produce a compliance-like claim
  from it.
- **Can model conservatively:** use a named, versioned scenario default
  with a stated value and rationale; tag every dependent finding
  `assumption` (per ADR-0002's typed-finding system).
- **Required for a meaningful review:** stop that portion of the review
  while still returning deterministic findings that don't depend on the
  field.

## Consequences

- Makes the `assumption` finding-type do real, defensible work instead of
  being a catch-all label.
- The PreflightGate node (ADR-0028, the system design notes) now
  branches three ways per missing field, not one.

## Full reasoning

See an independent design review §"ADR-0012."
