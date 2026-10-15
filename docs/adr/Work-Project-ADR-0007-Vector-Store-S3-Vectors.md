---
title: "ADR 0007: Vector Store — AWS S3 Vectors"
type: decision
tags: [adr, project, work-project, archibrief]
created: "2026-09-02"
updated: "2026-09-03"
status: accepted
---

# ADR 0007: Vector Store — AWS S3 Vectors

**Status:** Accepted (2026-09-02) — **amended by
[ADR-0042](Work-Project-ADR-0042-Minor-Amendments-Batch.md)** (2026-09-03): S3
Vectors choice stands; clarifies ordinary S3 is the immutable source of
truth and S3 Vectors is a rebuildable index on top, not the source of
truth itself.

## Context

Bedrock Knowledge Bases' default backend, OpenSearch Serverless, has a
hard floor of roughly $345-700/month (2 OCU minimum) regardless of actual
usage — a real, verified cost trap for a low-traffic portfolio project.
Aurora Serverless v2 + pgvector is cheaper but still has a small
always-on minimum-capacity cost. Third-party (Pinecone/Qdrant) steps
outside the AWS-native story for no clear benefit here.

## Decision

**AWS S3 Vectors** — no fixed floor, scales to near-zero at idle,
officially supported as a Bedrock Knowledge Base backend, stays fully
AWS-native. Best fit given the already-locked serverless-everything
compute decision (ADR-0005).

## Consequences

- Directly solves the day-one cost-control goal (ADR-0011).
- Embedding model choice and exact RAG ingestion pipeline design remain
  open, separate decisions.

## Full reasoning

See the project decision log §"W1-W4 stack research findings" and
Research Work Vector Store.
