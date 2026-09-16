---
title: "ADR 0020: RAG Ingestion and Chunking Strategy"
type: decision
tags: [adr, project, work-project, archibrief]
created: "2026-09-03"
updated: "2026-09-03"
status: accepted
---

# ADR 0020: RAG Ingestion and Chunking Strategy

**Status:** Accepted (2026-09-03) — **chunking approach corrected by
[[Work-Project-ADR-0036-Structure-Aware-Chunking-Baseline]]** (2026-09-03):
the "512-token recursive splitting always beats semantic chunking" claim
was an overgeneralization; replaced with a structure-aware baseline and
expanded citation metadata. Incremental-sync approach stands.

## Context

Needed a concrete approach for turning the curated AWS/security knowledge
base into searchable chunks. Largely settled by current best practice
rather than a preference call: a Feb 2026 benchmark validated recursive
character splitting at ~512 tokens with 50-100 token overlap at 69%
end-to-end accuracy, beating semantic chunking (54%), with zero extra
model calls required.

## Decision

- **Chunking:** recursive character splitting, ~512 tokens, 50-100 token
  overlap.
- **Metadata captured at ingestion:** source document, section, and
  timestamp, carried through to every chunk — this is what lets a
  finding cite an exact passage (ADR-0002's typed-evidence requirement)
  rather than just "somewhere in the AWS docs."
- **Update approach:** incremental sync — only new/changed documents get
  reprocessed, not the full corpus on every run.

## Consequences

- Keeps ingestion cost proportional to what actually changed, not to
  total corpus size — relevant to the day-one cost-control goal
  (ADR-0011).

## Full reasoning

See `AI-Drafts/Claude/work-project-stack-planning-qa.md` §"Round 2,"
question 5.
