# ADR 0007: Vector Store — AWS S3 Vectors

**Status:** Accepted (2026-09-02) — **amended by
[ADR-0042](0042-minor-amendments-batch.md)** (2026-09-03): S3
Vectors choice stands; clarifies ordinary S3 is the immutable source of
truth and S3 Vectors is a rebuildable index on top, not the source of
truth itself.

## Context

Bedrock Knowledge Bases' default backend, OpenSearch Serverless, has a
hard floor of roughly $345-700/month (2 OCU minimum) regardless of actual
usage — a real, verified cost trap for a low-traffic project.
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
