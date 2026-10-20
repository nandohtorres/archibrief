# ADR 0017: Application Database — DynamoDB

**Status:** Accepted (2026-09-03) — **cost justification corrected by
[ADR-0034](0034-aurora-cost-comparison-corrected.md)** (2026-09-03):
the DynamoDB choice stands, but the "~50x cheaper"/"$43+/mo Aurora floor"
claim was stale.

## Context

Needed a store for user accounts and review history (distinct from the
S3 Vectors RAG store, ADR-0007). Weighed DynamoDB vs. Aurora Serverless
v2 (Postgres). At low, intermittent traffic, DynamoDB is roughly 50x
cheaper than Aurora (near-$0 idle vs. Aurora's real $43+/mo floor even
idle). Aurora only wins for workloads needing real SQL joins/complex
relational queries.

## Decision

**DynamoDB.** This app's data shape (accounts, review records, findings)
doesn't need relational joins. Fits the serverless-everything
architecture (ADR-0005) and the cost-control goals (ADR-0011, ADR-0024).

## Consequences

- No relational query capability if a future feature genuinely needs it —
  would require a real architectural addition, not a config change.
