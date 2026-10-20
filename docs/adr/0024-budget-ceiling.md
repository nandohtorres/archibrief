# ADR 0024: Budget Ceiling — $50/month Target

**Status:** Accepted (2026-09-03) — **framing superseded by
[ADR-0040](0040-budget-as-target-real-cost-reporting.md)**
(2026-09-03): the $50 target stands, but "enforced ceiling" language was
corrected, and real-measured-cost reporting was explicitly locked (no
retroactive tailoring of the reported figure).

## Context

The original planning round found a realistic target of ~$50-75/mo
achievable given the S3 Vectors (ADR-0007) and DynamoDB (ADR-0017)
choices, but no hard number had been set as an actual enforced threshold.

## Decision

**$50/month** as the target AWS Budgets alert threshold. Explicit
direction if real costs come in under pressure: **tighten the number
further rather than raise it** — a smaller real number under genuine
constraint is a stronger engineering result ("this runs under
$30/month") than a looser one. Revisit and lower if costs allow,
raise only if genuinely necessary.

## Consequences

- Reinforces ADR-0011's rate-limiting requirements — the $50 target is
  only achievable with those limits actually enforced.
- A cost log tracks whether this target is actually being met once real
  spend starts.
