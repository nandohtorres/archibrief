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
[ADR-0042](Work-Project-ADR-0042-Minor-Amendments-Batch.md)** (2026-09-03): Terraform
choice stands; adds pinned CLI/provider constraints for ArchiBrief's own
infra and a "report, don't trust/install" rule for user-submitted
Terraform versions.

## Context

Needed one IaC tool, shared with the author's personal-website project so there's only one
to learn deeply. Candidates: Terraform vs. AWS CDK.

## Decision

**Terraform** primary. CDK optional/secondary only. Terraform is the most
widely used cloud-agnostic IaC tool, covers every AWS service this
project uses, and keeps the infrastructure reviewable as plain HCL — the
same format ArchiBrief itself reviews.

## Consequences

- Shared decision with the personal-website project — same tool learned once,
  reused across both projects.
- ArchiBrief's own input format is explicitly Terraform (bounded repo +
  workload brief) — this decision is doubly load-bearing since it's both
  the build tool and the product's primary input format.

## Full reasoning

See the project's private research notes.
