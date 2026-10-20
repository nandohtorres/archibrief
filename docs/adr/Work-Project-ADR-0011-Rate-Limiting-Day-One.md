---
title: "ADR 0011: Rate Limiting and Cost Controls From Day One"
type: decision
tags: [adr, project, work-project, archibrief, security]
created: "2026-09-02"
updated: "2026-09-03"
status: accepted
---

# ADR 0011: Rate Limiting and Cost Controls From Day One

**Status:** Accepted (2026-09-02) — **framing superseded by
[ADR-0030](Work-Project-ADR-0030-Rate-Limiting-Reframed.md)** (2026-09-03): the
day-one requirement itself stands, but "AWS-level limits as guaranteed
ceiling" was corrected.

## Context

The app becomes public and other people will actually run reviews
through it. Bedrock/OpenSearch cost-trap research (ADR-0007) showed how
easily a managed AI service can generate surprise billing.

## Decision

Both **AWS-service-level limits** (Bedrock invocation quotas, API
Gateway throttling, AWS Budgets alerts) **and app-level limits**
(per-user/IP/day request caps) are required from the first deployed
version — not progressive hardening added later, once core logic works.

## Consequences

- Directly protects against the OpenSearch-style cost-floor risk
  (avoided architecturally by ADR-0007, but this is the operational
  backstop).
- No hard dollar ceiling set yet as an actual AWS Budgets alert
  threshold — target is ~$50-75/month, not yet turned into an enforced
  number (open item).

## Full reasoning

See the project decision log §"Locked decisions" (security bullet).
