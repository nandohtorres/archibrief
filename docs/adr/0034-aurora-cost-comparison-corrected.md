# ADR 0034: Corrected Aurora Cost Comparison

**Status:** Accepted (2026-09-03) — **supersedes** ADR-0017's cost
justification only; the DynamoDB decision itself stands

## Context

Verified directly against AWS's Aurora Serverless v2 documentation:
supported engine versions can auto-pause to 0 ACUs with **no instance-
capacity charge** while paused (real caveats: breaks if there are open
connections, replication, an RDS Proxy, or Aurora Global Database
involved). ADR-0017's "$43+/month idle floor" and "~50x cheaper" claims
were stale/inaccurate.

## Decision

**DynamoDB remains the choice**, but on corrected grounds: operational
fit for this app's access patterns (no relational-join need identified),
not a 50x cost advantage that doesn't actually hold once Aurora's
auto-pause is accounted for. Design tables from access patterns first.
Cognito owns authentication identities; DynamoDB stores the application
profile, entitlements, job metadata, counters, and review indexes. Store
large payloads (full input archives, reports, evidence ledgers) in S3
with pointers in DynamoDB — a DynamoDB item is capped at 400 KB. Include
ownership checks in every key pattern, TTLs for transient jobs, and
idempotent job creation.

## Consequences

- The DynamoDB data models gain the ownership-check/TTL/idempotency
  requirements.
- No architecture change — this ADR only corrects the stated reasoning.
