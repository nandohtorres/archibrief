---
title: "ADR 0027: Untrusted Terraform Ingestion + Evidence Reproducibility Contracts"
type: decision
tags: [adr, project, work-project, archibrief, security]
created: "2026-09-03"
updated: "2026-09-03"
status: accepted
---

# ADR 0027: Untrusted Terraform Ingestion + Evidence Reproducibility Contracts

**Status:** Accepted (2026-09-03) — **extends** ADR-0002, doesn't reverse it

## Context

Codex's independent review ([[Work-Project-ADR-Review-Codex]]) identified
a real gap: nothing in the original design prohibited executing
user-submitted Terraform (`terraform init`/`plan`/`apply`, provisioners,
external data sources), which would cross a real software-supply-chain
and network trust boundary — `terraform init` retrieves remote modules
and installs provider plugins. Separately, "exact citation" was promised
(ADR-0002) without a defined reproducibility contract.

## Decision

**Untrusted-repository contract:** parse submitted HCL statically only.
Never run `terraform init`, `plan`, `apply`, provisioners, or external
data sources on submitted content. Reject path traversal, symlinks
escaping the extraction root, archive bombs, oversized files, binaries,
unsupported encodings. Remote-module internals are `not-observable`
unless a separate, tightly allowlisted resolver is designed later —
preferable to executing/downloading untrusted dependencies.

**Evidence-reproducibility contract:** every citation carries source URL,
source edition/version or retrieved-at date, section identity, chunk
identity or content hash, and the exact quoted span — not just a URL plus
current chunk text (which breaks once AWS edits the source page).

## Consequences

- Directly closes the gap flagged in the cross-decision tensions table
  (0002+0015+0022).
- Feeds into ADR-0038 (prompt-injection architectural boundaries) and
  ADR-0033/System Design's Ingest node.

## Full reasoning

See [[Work-Project-ADR-Review-Codex]] §"ADR-0002."
