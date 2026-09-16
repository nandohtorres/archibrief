---
title: "ADR 0001: Product Name and Framing"
type: decision
tags: [adr, project, work-project, archibrief]
created: "2026-09-02"
updated: "2026-09-03"
status: accepted
---

# ADR 0001: Product Name and Framing

**Status:** Accepted (2026-09-02)

## Context

Working name "ArchGuard AI" was reconsidered after a differentiation
research pass. A candidate name check ("ArchGuard.io" as a supposed
existing competitor) turned out to be a fabricated research finding,
independently verified false. Separately, "ArchiAudit" was considered but
raised a real framing problem: the product is not a credentialed audit.

## Decision

Product is named **ArchiBrief**. Framing deliberately avoids the word
"audit" anywhere in the name or positioning — the product produces typed,
cited findings with stated confidence, not a certification/attestation.

## Consequences

- Domain verified available across `.com`/`.io`/`.ai` via direct DNS (not
  just search-tool summary) — final registration in Cloudflare still
  pending as an action item.
- The "never label a design compliant" rule (ADR-0003) is reinforced by
  this naming choice, not a separate concern.

## Full reasoning

See [[Work-Project]] §"Product direction" for the full naming trail
(Architext → ArchiDocs → ArchiAudit rejected → ArchiBrief) and the
archguard.io hallucination incident.
