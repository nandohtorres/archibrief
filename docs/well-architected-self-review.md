# ArchiBrief reviewed against the AWS Well-Architected Framework

ArchiBrief reviews other people's AWS designs against the Well-Architected
Framework, so it should hold up to the same review. This is that review:
what each pillar asks, what ArchiBrief does, and where it falls short.
Evidence links point at code, tests or decision records. Updated 2026-10-29.

The scale matters for every judgment below: a single-owner portfolio
service with a few dozen reviews a day, a $75 monthly spend ceiling and one
Region. Several gaps would be fixed first at a larger scale, and are
accepted here on purpose.

## Summary

| Pillar | Strongest point | Biggest gap |
|---|---|---|
| Operational excellence | Everything is Terraform; 58 decision records; CI gates every change | Backend deploys are manual; no alarm on failed reviews |
| Security | Untrusted input never executes, and the model can't change anything | Review keys in `localStorage` are readable by any script in the page |
| Reliability | No paid step is ever retried blindly; a failed model step still ships a report | One Region; Lambda concurrency can't be reserved in this account |
| Performance efficiency | Static frontend on a CDN; serverless backend; streamed model call | A review takes minutes, and nothing has been load-tested |
| Cost optimization | Spend reserved before every paid call, with a monthly ceiling and an automatic stop | Reservations are estimates, never settled to the actual bill |
| Sustainability | Scale to zero; no idle compute | The largest model in use for every review, without a measured smaller alternative |

## Operational excellence

**Doing well**

- All infrastructure is Terraform (`infra/`), reviewed as a plan before
  every apply.
- Every architectural decision has a record with context, alternatives and
  consequences; superseded decisions link forward ([ADRs](adr/README.md)).
- CI on every pull request: backend tests (pytest with moto, the trap and
  adversarial suites), frontend unit tests, Playwright with accessibility
  checks, `tflint` and Trivy over our own infrastructure, Gitleaks. `master`
  requires all five jobs.
- The frontend deploys itself after green CI, and a daily smoke test checks
  the live site with no credentials (ADR-0055).
- Failures are logged as stage plus error class only, so logs never carry
  submitted content.
- Live hard tests with answer keys find what unit tests can't, and each one
  has turned into a recorded fix ([evaluation](evaluation.md#live-hard-tests)).

**Gaps**

- Backend deploys are manual: build packages, plan, apply. Fine for one
  owner; a team would want a pipeline with a plan approval step.
- No alarm fires when a review fails or falls back to rules only; failures
  are found by reading logs. (Parked: it needs deploy-policy changes.)
- No tracing across Step Functions, Lambda and AgentCore (X-Ray parked).

## Security

**Doing well**

- **Untrusted input never executes.** Terraform is parsed statically;
  providers, provisioners and remote modules never run (ADR-0027). Trivy
  runs in its own Lambda with no AWS credentials and no network (ADR-0048).
- **The model can't act.** Its only output is one schema-checked tool call,
  and the runtime's role is read and invoke only (threat model, LLM06).
- **The model never reads the code.** It gets a summary built from
  allowlists and fixed vocabularies; names are capped at 32 identifier
  characters (ADR-0049, ADR-0056).
- **Defense in depth for prompt injection:** Guardrails twice, untrusted
  data labeled as data, the brief can't narrow the review, and every quote
  is checked server-side (ADR-0038, ADR-0058).
- **Least privilege:** one role per Lambda, scoped to what its code does; a
  permissions boundary on every runtime role that the deploy identity
  can't remove; the CD role can only write the site bucket (ADR-0055).
- **Capabilities, not accounts:** random read/write keys, only hashes stored,
  writes bound to the original network; share links keep the read key in
  the URL fragment (ADR-0053).
- Content stays out of Step Functions history; uploads are checksum-bound
  and can't be overwritten.

**Gaps**

- Review keys live in `localStorage` for seven days, so an XSS would expose
  them. React escapes output and the model never produces HTML, but the
  Content Security Policy allows inline scripts (`'unsafe-inline'`, which
  the static export's inline bootstrap needs), so it wouldn't stop one.
- The visitor-hash and reservation keys are Terraform-generated Lambda
  environment values, readable by anyone who can read the functions'
  configuration (accepted: only the owner can).
- The corpus is rebuilt from AWS pages without a review of what changed
  between versions.

## Reliability

**Doing well**

- **Idempotent by construction:** server-issued review IDs, stable Step
  Functions execution names, conditional claims in DynamoDB, a client nonce
  that recovers a lost upload response.
- **No blind retries of paid work.** Non-paid stages retry transient errors;
  the model call runs once, because a timed-out call may already be billed.
- **Timeouts nest:** the streamed model call ends at 420 s, the worker waits
  up to 600 s bounded by its remaining time, the Lambda times out at 900 s,
  the state machine task at 910 s (ADR-0058).
- **Graceful degradation:** a Trivy failure falls back to ArchiBrief's own
  rules; a model failure ships the rule findings with a clear note.
- "Go deeper" runs as a durable background job whose result and completion
  commit atomically; reloading recovers it.

**Gaps**

- One Region (us-east-1). A Regional Bedrock or AgentCore outage stops new
  reviews; saved reports stay readable from S3 and DynamoDB.
- Lambda concurrency can't be reserved for the pipeline (this account's
  concurrency ceiling is below AWS's minimum), so a flood on one function
  could starve another (threat model T4).
- After the budget's automatic stop, the kill switch stays on until the
  owner turns it off.

## Performance efficiency

**Doing well**

- The frontend is a static export on S3 behind CloudFront; Lighthouse on
  the live site scored 100 in all four desktop categories and 93 for mobile
  performance
  ([browser evidence](evidence/browser-results.md)).
- Serverless backend sized per function: Trivy gets more memory for CPU,
  small stages get 256 MB.
- The model call streams, so a long answer finishes instead of timing out;
  the chat caches the review block across questions.
- Retrieval uses a vector index plus a lexical companion index, measured at
  89% hit rate at 5 on a development set and 86% on a held-out set.

**Gaps**

- A review takes a few minutes, mostly the model. The progress screen shows
  the diagram early, but not the rule findings.
- Nothing has been load-tested; the limits keep load far below where it
  would matter.

## Cost optimization

**Doing well**

- **Spend is reserved before it happens:** every paid path reserves its
  estimate against a $75 monthly ceiling, daily, per-visitor and per-review
  limits in one DynamoDB transaction (ADR-0052).
- **An automatic stop:** at 90% of the $100 AWS budget, a Lambda turns the
  kill switch on.
- **Pay per use:** Lambda, Step Functions, DynamoDB on demand, S3 Vectors;
  no instance runs while nobody is reviewing.
- **The demos cost nothing to open:** they load saved reports, and their
  suggested chat answers were generated once.
- Per-call bounds: max tokens, at most 12 model findings, a deadline, no
  retries.

**Gaps**

- Reservations are fixed estimates ($0.40 per review) and are never settled
  to the actual Bedrock bill, so real spend can differ from what the limits
  count.
- Fixed monthly costs (WAF's web ACL and rules, CloudWatch logs) aren't
  tracked against the ceiling, which only sees estimated paid-call spend.

## Sustainability

**Doing well**

- Scale to zero everywhere; the only always-on pieces are managed services
  (CloudFront, API Gateway, WAF).
- Deterministic checks run before the model, and the model reads a summary
  rather than the whole codebase, so each call processes less.
- S3 lifecycle rules delete review data after seven days.

**Gaps**

- Every review uses Claude Sonnet. A smaller model for the first pass, with
  Sonnet for "go deeper", hasn't been measured.

## First changes at a larger scale

1. An alarm on failed and rules-only reviews, and a dashboard of review
   outcomes.
2. Settle reservations to measured cost per review, and alert when the two
   drift.
3. A backend pipeline with a plan-approval step.
4. Reserved concurrency for the review pipeline (after an account limit
   increase).
5. A measured smaller-model first pass.
