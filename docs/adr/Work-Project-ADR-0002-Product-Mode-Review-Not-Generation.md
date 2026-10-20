---
title: "ADR 0002: Product Mode — Review, Not Generation"
type: decision
tags: [adr, project, work-project, archibrief]
created: "2026-09-02"
updated: "2026-09-03"
status: accepted
---

# ADR 0002: Product Mode — Review, Not Generation

**Status:** Accepted (2026-09-02) — **extended by
[ADR-0027](Work-Project-ADR-0027-Untrusted-Terraform-Ingestion-Contract.md)**
(2026-09-03): the review-mode decision stands; ADR-0027 adds the
untrusted-ingestion and evidence-reproducibility contracts this mode
needed but didn't originally define.

## Context

Original concept leaned toward generating an AWS architecture from a
scenario description. Differentiation research found real AWS/third-party
tools (AWS Startup Advisor, Amazon Q, Well-Architected Generative AI Lens)
already occupy the "generate-from-scratch advisor" space credibly, backed
by real account access and actual AWS expertise — a free, first-party
competitor.

## Decision

Primary interaction is **evaluating an existing/described design**
(bounded Terraform repo + workload brief), not generating one from
scratch. Generation-from-scratch is explicitly deferred out of v1 as a
possible future mode built on the same trusted review core.

The differentiator is **reproducible, typed evidence**: every finding
typed (observed fact / deterministic-rule result / inference / assumption
/ recommendation / not-observable), cited to an exact source passage,
confidence derived from real signals, alternatives-considered shown. A
published benchmark (seeded good/bad designs, tracked false-positive rate)
is a launch criterion.

## Consequences

- Positions against AWS Startup Advisor without competing head-on for the
  same "advisor" framing.
- Every output format downstream (evidence ledger, IAM checklist, business
  case) inherits the same typed/cited/confidence-scored discipline.

## Full reasoning

See the project decision log §"Product direction" and the private
competitive-research notes that drove this.
