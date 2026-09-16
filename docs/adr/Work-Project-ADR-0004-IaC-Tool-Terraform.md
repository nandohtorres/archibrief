---
title: "ADR 0004: IaC Tool — Terraform"
type: decision
tags: [adr, project, work-project, archibrief, terraform]
created: "2026-09-02"
updated: "2026-09-03"
status: accepted
---

# ADR 0004: IaC Tool — Terraform

**Status:** Accepted (2026-09-02) — **amended by
[[Work-Project-ADR-0042-Minor-Amendments-Batch]]** (2026-09-03): Terraform
choice stands; adds pinned CLI/provider constraints for ArchiBrief's own
infra and a "report, don't trust/install" rule for user-submitted
Terraform versions.

## Context

Needed one IaC tool, shared with [[Personal-Website]] so there's only one
to learn deeply. Candidates: Terraform vs. AWS CDK.

## Decision

**Terraform** primary. CDK optional/secondary only. Answered as a
side-finding across the P-SYNTH career-positioning research rather than a
dedicated research pass — Terraform showed up consistently as the
expected/recognized tool across the target-role research.

## Consequences

- Shared decision with [[Personal-Website]] — same tool learned once,
  reused across both projects.
- ArchiBrief's own input format is explicitly Terraform (bounded repo +
  workload brief) — this decision is doubly load-bearing since it's both
  the build tool and the product's primary input format.

## Full reasoning

See [[Research-Findings-Positioning-Synthesis]] §3.
