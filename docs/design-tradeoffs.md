# Design trade-offs on one page

The decisions that shaped ArchiBrief, what was given up for each, and what
would make it the wrong call. Each links to its full decision record.

| Decision | Chosen over | Why | What it costs | Revisit if |
|---|---|---|---|---|
| **Review, don't generate** ([ADR-0002](adr/0002-product-mode-review-not-generation.md)) | Generating architectures from a prompt | A second opinion with evidence is checkable; generated designs aren't | Users must already have Terraform | People ask for greenfield designs more than reviews |
| **Deterministic rules first, model second** ([ADR-0048](adr/0048-trivy-scanner-in-the-review-pipeline.md)) | A model-only review | Rule findings are repeatable, free and don't depend on the brief | Two systems to maintain, and their findings can overlap | A model reliably matches the rules' precision |
| **The model reads a summary, never the code** ([ADR-0049](adr/0049-resource-summary-for-reasoning.md), [ADR-0056](adr/0056-resource-summary-details-declared-context-and-risk-ordered-cap.md)) | Sending the raw Terraform | Raw code is a prompt-injection channel; a fixed-vocabulary summary isn't | The model only knows what the summary extracts; unsupported types are blind spots | Extraction can't keep up with the resource types people submit |
| **Quotes must match retrieved text** ([ADR-0038](adr/0038-prompt-injection-architectural-boundaries.md)) | Trusting model citations | Makes fabricated sources impossible to publish | Proves where a quote came from, not that it supports the claim | Semantic support can be checked cheaply |
| **Serverless: Lambda, Step Functions, AgentCore** ([ADR-0005](adr/0005-compute-serverless.md), [ADR-0028](adr/0028-orchestration-ownership-boundary.md)) | ECS or EKS | Scales to zero for a bursty, low-volume service; durable workflow state for free | Cold starts, per-service timeouts to nest, more moving parts to wire | Steady traffic makes always-on compute cheaper |
| **Content outside workflow history** ([ADR-0028](adr/0028-orchestration-ownership-boundary.md)) | Passing briefs and findings through Step Functions | Execution history can't be deleted early; keeping it to IDs keeps retention promises | An extra worker Lambda and S3 reads | Never, while reviews carry user content |
| **No accounts; capability keys** ([ADR-0046](adr/0046-public-reviews-and-grounded-chat.md), [ADR-0053](adr/0053-review-urls-and-read-only-share-links.md)) | Cognito sign-up | Nobody signs up to try a portfolio tool; no passwords to protect | Keys in the browser; a cleared browser loses access; links can't be revoked early | Reviews need to persist past seven days or across devices |
| **Reserve spend before paid calls** ([ADR-0052](adr/0052-monthly-spend-ceiling-and-automatic-kill-switch.md)) | Relying on AWS Budgets | Billing lags by hours; a transaction before each call is real time | Reservations are estimates, not the actual bill | Per-review cost varies enough that estimates mislead |
| **Never retry a paid call** ([ADR-0058](adr/0058-streamed-reasoning-findings-cap-and-rules-only-fallback.md)) | Automatic retries | A timed-out call may already be billed; a retry could charge twice | A transient failure costs the visitor the AI half of a review | The model API supports idempotent requests |
| **Ship rules-only when the model fails** ([ADR-0058](adr/0058-streamed-reasoning-findings-cap-and-rules-only-fallback.md)) | Failing the review | The rule findings are already final; some evidence beats none | A visitor might read a rules-only report as complete, so it's labeled | Model failures become rare enough not to matter |
| **Ask the one un-inferable question up front** ([ADR-0054](adr/0054-regulatory-question-up-front-no-review-pause.md)) | Pausing a review to ask | No review waits on the visitor; less infrastructure | One more required field on the form | Several fields turn out to need answers |
| **S3 Vectors for retrieval** ([ADR-0007](adr/0007-vector-store-s3-vectors.md)) | OpenSearch Serverless | No minimum monthly cost for a small, fixed corpus | Fewer query features | The corpus grows or needs hybrid ranking in one service |
| **Frontend CD, backend by hand** ([ADR-0055](adr/0055-frontend-continuous-deployment-with-scoped-oidc.md)) | Full CD | A frontend mistake is a revert; a backend mistake can delete data, so a person reads the plan | Slower backend releases | More than one person ships backend changes |

## Patterns worth reusing

- **Untrusted input becomes facts, never text,** before a model sees it.
  Allowlists and fixed vocabularies close the injection channel without
  hiding the configuration.
- **Reserve, then spend.** One transaction across every limit, before the
  paid call, with the claim kept so a duplicate can't dispatch again.
- **Degrade to what's already certain.** When the expensive step fails,
  publish the cheap, deterministic part and say what's missing.
- **Test with answer keys, not just assertions.** Planted-issue submissions
  scored by hand found four problems that 1,272 unit tests didn't
  ([live hard tests](evaluation.md#live-hard-tests)).
