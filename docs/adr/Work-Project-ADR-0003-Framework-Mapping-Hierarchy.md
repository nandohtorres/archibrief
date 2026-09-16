---
title: "ADR 0003: Framework Mapping Hierarchy"
type: decision
tags: [adr, project, work-project, archibrief]
created: "2026-09-02"
updated: "2026-09-03"
status: accepted
---

# ADR 0003: Framework Mapping Hierarchy

**Status:** Accepted (2026-09-02) — **amended by
[[Work-Project-ADR-0042-Minor-Amendments-Batch]]** (2026-09-03): the
hierarchy stands; adds a more precise AWS-specific ordering for
observable-configuration findings.

## Context

Needed a defensible, non-overclaiming way to map findings to real
frameworks/standards, without asserting compliance the product can't
actually certify.

## Decision

1. **AWS Well-Architected Framework** — primary rubric, ties to SAA-C03.
2. **CIS Controls v8** — secondary security cross-reference.
3. **NIST CSF 2.0** — optional, executive-communication framing only.
4. **CompTIA Security+ SY0-701 domains** — opt-in, clearly-labeled
   educational metadata only.
5. Secondary by finding type: OWASP Top 10/ASVS (app-layer), NIST SSDF
   (CI/CD evidence), AWS Foundational Security Best Practices/Security Hub
   (AWS-native grounding).
6. Deliberately excluded: SOC 2, ISO 27001 (too heavy/audit-scale), NIST
   800-53 (federal-specific, ties to deprioritized clearance track).

Never label a design "compliant" — findings relate to a framework outcome;
state what additional evidence would be needed to actually assess it.

## Consequences

- Reinforces ADR-0001's "not an audit" framing.
- Security+ is explicitly downgraded to secondary/educational after a
  dedicated research pass found it not viable as a primary technical
  mapping.

## Full reasoning

See [[Work-Project]] §"Product direction" and
[[Research-ArchGuard-Differentiation-Claude]] (includes the Security+
domain-mapping viability research pass).
