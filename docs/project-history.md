# How ArchiBrief evolved

The decision records say what was decided. This page puts them in order:
what the project set out to do, where the plan met reality, and what changed
as a result. Dates come from the ADRs and the commit history. Each turn links
to its full record.

## 1. Choosing the problem (late August to September 2)

The project started as "ArchGuard AI", an assistant that would generate AWS
architectures from a prompt. Research before any code found that AWS and
third-party tools already cover that closely. The product was reshaped
rather than just renamed: ArchiBrief **reviews an existing Terraform
design against a workload brief** instead of generating one
([ADR-0001](adr/0001-product-name-and-framing.md),
[ADR-0002](adr/0002-product-mode-review-not-generation.md)). A review with
evidence can be checked; a generated design can't.

**Why it matters:** the first decision was a product decision, made from
research rather than enthusiasm for the original idea.

## 2. Designing before building (September 2 to 11)

44 ADRs were written before the first commit: Terraform, serverless
compute, Bedrock, S3 Vectors, LangGraph on AgentCore, the prompt-injection
boundary, the threat-modeling method and a budget target. Several were
corrected within days by follow-up research, and the corrections were
recorded as new ADRs instead of quiet edits:

- Hugging Face plan corrected to Guardrails ([ADR-0033](adr/0033-hugging-face-path-corrected.md)).
- Aurora cost comparison corrected ([ADR-0034](adr/0034-aurora-cost-comparison-corrected.md)).
- The budget became a target with real measured cost reported, not a promise
  ([ADR-0040](adr/0040-budget-as-target-real-cost-reporting.md)).

**Why it matters:** decisions are immutable and superseded in the open, so
the record shows how the thinking changed, not only where it ended.

## 3. Cutting accounts (September 11)

The plan called for Cognito accounts with passwords and emailed codes
([ADR-0018](adr/0018-auth-provider-cognito.md),
[ADR-0043](adr/0043-auth-method-simplified-password-plus-email-code.md)).
Nobody signs up to try a portfolio tool, and accounts add passwords to
protect. Accounts were cut for an owner-only key
([ADR-0044](adr/0044-no-user-accounts-admin-pre-shared-credential.md)).

## 4. Building it (September 16 to October 17)

The repository history starts September 16 with the core pipeline: bounded
Terraform ingestion, the rule engine, retrieval and the reasoning step.
The main build sprint followed in October:

- direct S3 uploads ([ADR-0045](adr/0045-archive-path-direct-upload.md))
- Trivy as the deterministic core ([ADR-0048](adr/0048-trivy-scanner-in-the-review-pipeline.md))
- a sanitized resource summary for the model instead of raw code ([ADR-0049](adr/0049-resource-summary-for-reasoning.md))
- grounded report chat ([ADR-0050](adr/0050-grounded-chat-build.md))
- stakeholder cost view ([ADR-0051](adr/0051-stakeholder-costs.md))

## 5. Opening to the public (October 15 to 26)

Anonymous public reviews were designed with layered limits: Turnstile,
WAF, and spend reserved in DynamoDB before every paid call
([ADR-0046](adr/0046-public-reviews-and-grounded-chat.md)). Submissions
opened to the public on **October 23**, and the admin key was retired.
A $75 monthly ceiling and an automatic kill switch at 90% of the AWS budget
followed on October 26
([ADR-0052](adr/0052-monthly-spend-ceiling-and-automatic-kill-switch.md)).

Removing the review pause: the earlier design stopped a review to ask the
visitor a question. It was replaced by one required question on the form,
removed in two safe stages
([ADR-0054](adr/0054-regulatory-question-up-front-no-review-pause.md)).

## 6. Testing it like an adversary (October 28 to November 2)

Three planted-issue Terraform submissions with answer keys were run through
the live site. Each broke something the unit tests had not
([case study](case-study.md#testing-it-like-an-adversary)):

- The model was blind to nested configuration
  ([ADR-0056](adr/0056-resource-summary-details-declared-context-and-risk-ordered-cap.md)).
- Retrieval needed topic searches by resource type
  ([ADR-0057](adr/0057-retrieval-topic-searches-and-citation-rules.md)).
- Large reviews timed out. Streaming was tried, failed live and was reverted
  to one bounded, non-streaming call with a rules-only fallback
  ([ADR-0058](adr/0058-streamed-reasoning-findings-cap-and-rules-only-fallback.md),
  [ADR-0059](adr/0059-non-streaming-reasoning-and-bounded-model-input.md),
  [incident](incidents/2026-10-29-review-timeouts.md)).
- A polite, misleading brief steered the review.
- The summary cap cut resources alphabetically.

On November 2 a deploy shipped a runtime that crashed on a missing parser
module. The rules-only fallback kept reviews publishing while it was fixed,
and the runtime now has an import test so that can't recur.

**Why it matters:** answer-key testing found four problems that 1,272
unit tests didn't.

## 7. Narrowing scope to raise accuracy (November 10, in progress)

The hard tests also showed the limit of the current approach. On the
119-resource test, the review still missed a data-residency breach and four
critical issues, because the model can only reason about what the summary
shows it, and large configurations hit caps on resources, facts and
findings. In the review logs from October 12 to November 2, the only two
submissions whose size was recorded had 69 and 119 resources.

The decision: focus on developers reviewing **small AWS workloads**
(startups, solo developers, students), with a provisional limit of **50
resource declarations per review**, and spend the effort on measured
accuracy instead of breadth
([ADR-0061](adr/0061-small-workload-accuracy-pilot.md)). The plan, in order:

1. **Show exactly what was reviewed:** "Reviewed 47 of 50 declarations",
   with modules that couldn't be read listed as a labeled partial review.
2. **Measure a baseline** against written answer keys before changing
   anything.
3. **Enforce the limit before any paid call**, with a clear message.
4. **Test a second AI pass** that checks each finding against the
   configuration and its cited source, and ship it only if it reduces wrong
   findings without losing Critical or High catches.

Larger limits (75, then 100) are a later, measured step, not a promise.

The plan itself went through several review rounds between two AI assistants,
with the owner deciding each trade-off. The first detailed build contract was
correct but over-built (request hashing through the paid AI path, a public API
and UI for a phase that shows nothing to users). It was cut back to the six
files the count actually needs, and a second review then caught eight real
errors in the slimmed version, such as non-AWS resources also being sent to the
model and a failed model call not proving nothing was sent. The principle that
came out of it: minimal changes, each one needed for the accuracy goal, and
every review must name the concrete failure it prevents.

**Why it matters:** this is the scope trade-off made on evidence: a tool
that is right about 50 resources is more useful than one that is vague
about 150.
