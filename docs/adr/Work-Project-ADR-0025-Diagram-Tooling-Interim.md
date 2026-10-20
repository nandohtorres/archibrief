---
title: "ADR 0025: Diagram Tooling — mingrammer/diagrams (Interim)"
type: decision
tags: [adr, project, work-project, archibrief]
created: "2026-09-03"
updated: "2026-09-03"
status: accepted
---

# ADR 0025: Diagram Tooling — mingrammer/diagrams (Interim)

**Status:** Accepted (2026-09-03), low priority — **amended by
[ADR-0042](Work-Project-ADR-0042-Minor-Amendments-Batch.md)** (2026-09-03): tooling
choice stands; clarifies the point is architecture communication, not
the library and clarifies this isn't a
head start on the future in-app diagram feature.

## Context

Two distinct needs exist: (a) the product's own future diagram-generation
feature (deferred past v1 per the project spec), and (b) practical
documentation diagrams needed now (READMEs, case study
write-ups). Options considered: `mingrammer/diagrams` (free, code-based
Python library, real AWS icon set), Cloudcraft (commercial, polished
isometric diagrams, popular among practicing SAs), draw.io/Lucidchart
(generic, manual).

## Decision

**`mingrammer/diagrams`** for current documentation needs — free,
code-based ("diagrams as code," versioned with the repo), reusable later
since ArchiBrief already parses Terraform and could eventually generate
diagrams directly from ingested IaC using a similar approach. No attempt
to build the product's own diagram feature yet — deliberately deferred,
pivot possible once that phase actually arrives.

## Consequences

- Low-stakes, easily revisited decision — explicitly not load-bearing
  for anything else in the architecture.

## Full reasoning

See `AI-Drafts/Claude/work-project-stack-planning-qa.md` §"Round 2,"
question 10.
