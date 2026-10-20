# ADR 0004: IaC Tool — Terraform

**Status:** Accepted (2026-09-02) — **amended by
[ADR-0042](0042-minor-amendments-batch.md)** (2026-09-03): Terraform
choice stands; adds pinned CLI/provider constraints for ArchiBrief's own
infra and a "report, don't trust/install" rule for user-submitted
Terraform versions.

## Context

Needed one IaC tool, ideally the same one used across related projects so
there is only one to learn deeply. Candidates: Terraform vs. AWS CDK.

## Decision

**Terraform** primary. CDK optional/secondary only. Terraform is the most
widely used cloud-agnostic IaC tool, covers every AWS service this
project uses, and keeps the infrastructure reviewable as plain HCL — the
same format ArchiBrief itself reviews.

## Consequences

- Same tool learned once and reused across related projects.
- ArchiBrief's own input format is explicitly Terraform (bounded repo +
  workload brief) — this decision is doubly load-bearing since it's both
  the build tool and the product's primary input format.
