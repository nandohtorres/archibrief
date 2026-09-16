---
title: "ADR 0040: Budget as Target/Alert Threshold; Real Measured Cost Reported"
type: decision
tags: [adr, project, work-project, archibrief, finops]
created: "2026-09-03"
updated: "2026-09-03"
status: accepted
---

# ADR 0040: Budget as Target/Alert Threshold; Real Measured Cost Reported

**Status:** Accepted (2026-09-03) — **supersedes** ADR-0024's "$50/mo
target" framing (the $50 number itself is unchanged)

## Context

Verified directly: AWS Budgets has no native action that halts Bedrock or
general serverless spend — it can apply IAM/SCP policies or target
specific EC2/RDS instances, nothing more direct. Calling $50 an "enforced
ceiling" overstated what AWS actually guarantees (ADR-0030 already
established this for rate limiting generally). Separately, Fernando
raised whether the *reported* "planned" budget figure could be adjusted
after the fact to sit closer to the real measured cost, for narrative
effect. After discussion, confirmed: the **real, measured cost is always
what gets reported** — no retroactive tailoring of a claimed "planned"
number. There was never a formally published estimation methodology to
misrepresent, so this is a low-stakes packaging choice, not an integrity
issue — but the actual dollar figure reported publicly is the real one,
not a massaged one.

## Decision

- $50/month is a **target and alert threshold**, not a guaranteed
  ceiling — the real enforcement layer is ADR-0030's application-level
  controls, not AWS Budgets itself.
- Track two numbers separately: **fixed/standing monthly cost** (domain/
  DNS, logs/retention, alarms, storage, secrets, WAF/API, imported-model
  storage) and **marginal cost per review** (guest/standard/deep,
  including retries, classifier/guardrail calls, embeddings/retrieval,
  reasoning tokens, AgentCore Runtime, observability).
- [[Work-Project-Cost-Log]] reports the **real, actual measured cost**,
  whatever it turns out to be — never adjusted after the fact for
  narrative/optics purposes. Tighten the *target* over time if real
  measurements support it (per ADR-0024's original reasoning), but the
  actual reported number is always the real one.
- Set multiple alert tiers below and at the target; test the application
  kill switch (ADR-0030) as a real, verified control, not just a
  documented intention.

## Consequences

- Directly reinforces the honesty/typed-evidence positioning that is
  this product's core differentiator (ADR-0002) — applied to Fernando's
  own project reporting, not just the product's output.

## Full reasoning

See [[Work-Project-ADR-Review-Codex]] §"ADR-0024" and conversation
2026-09-03 (the budget-honesty discussion, resolved directly with
Fernando).
