# ArchiBrief — Architecture Decision Records

One short, atomic file per real decision — Context / Decision /
Consequences / Status, following the standard ADR format (Michael
Nygard's original convention; see
[joelparkerhenderson/architecture-decision-record](https://github.com/joelparkerhenderson/architecture-decision-record)
for reference). Each ADR is **immutable once accepted** — if a decision
later changes, a new ADR supersedes it and links back rather than editing
history in place.

This folder intentionally stays terse: it doesn't restate the
back-and-forth, just the outcome and why. Amendments are recorded in
place with their date when they refine, rather than reverse, a decision.
File names are `NNNN-title.md`; ADRs reference each other as `ADR-NNNN`.

## Decisions

| # | Decision | Status |
|---|---|---|
| [ADR-0001](0001-product-name-and-framing.md) | Product name (ArchiBrief) and framing (not "audit") | Accepted |
| [ADR-0002](0002-product-mode-review-not-generation.md) | Review-mode primary, not generate-from-scratch | Accepted |
| [ADR-0003](0003-framework-mapping-hierarchy.md) | AWS WAF/CIS/NIST/Security+ mapping hierarchy | Accepted |
| [ADR-0004](0004-iac-tool-terraform.md) | Terraform over CDK | Accepted |
| [ADR-0005](0005-compute-serverless.md) | Serverless (Lambda/Step Functions) over ECS/Kubernetes | Accepted |
| [ADR-0006](0006-llm-provider-bedrock.md) | Bedrock-primary, provider-agnostic layer | Accepted |
| [ADR-0007](0007-vector-store-s3-vectors.md) | AWS S3 Vectors over OpenSearch Serverless | Accepted |
| [ADR-0008](0008-agent-framework-langgraph-agentcore.md) | LangGraph on Bedrock AgentCore | Accepted |
| [ADR-0009](0009-backend-language-python.md) | Python | Accepted |
| [ADR-0010](0010-auth-and-demo-access.md) | Real accounts + rate-limited guest mode | Superseded by 0044 |
| [ADR-0011](0011-rate-limiting-day-one.md) | Rate limiting/cost controls from day one | Accepted |
| [ADR-0012](0012-agentic-preflight-gate.md) | Baseline-data pre-flight gate, not open chat loop | Accepted |
| [ADR-0013](0013-ui-build-sequencing.md) | UI built early/in parallel, not deferred to end | Accepted |
| [ADR-0014](0014-hugging-face-capability.md) | Optional HF sub-task via Bedrock Custom Model Import; no self-training | Accepted |
| [ADR-0015](0015-public-repo-secrets-handling.md) | One real public repo, no dummy repo; standard secret hygiene | Accepted |
| [ADR-0016](0016-frontend-framework-nextjs.md) | Frontend framework — Next.js | Accepted |
| [ADR-0017](0017-application-database-dynamodb.md) | Application database — DynamoDB | Accepted |
| [ADR-0018](0018-auth-provider-cognito.md) | Auth provider — Amazon Cognito | Superseded by 0044 |
| [ADR-0019](0019-embedding-model-titan.md) | Embedding model — Titan V2 | Accepted |
| [ADR-0020](0020-rag-ingestion-chunking.md) | RAG ingestion/chunking strategy | Accepted |
| [ADR-0021](0021-iam-model-and-app-rbac.md) | IAM model + application-level RBAC (admin role) | AWS IAM portion stands; app-RBAC portion superseded by 0044 |
| [ADR-0022](0022-prompt-injection-defense.md) | Prompt-injection defense architecture | Accepted |
| [ADR-0023](0023-evaluation-depth-strategy.md) | Evaluation-depth strategy — lightweight first pass | Accepted, provisional |
| [ADR-0024](0024-budget-ceiling.md) | Budget ceiling — $50/month target | Accepted |
| [ADR-0025](0025-diagram-tooling-interim.md) | Diagram tooling — mingrammer/diagrams (interim) | Accepted |
| [ADR-0026](0026-documentation-structure.md) | Documentation structure — Journal + Spec + Build Plan + ADRs | Accepted |
| [ADR-0027](0027-untrusted-terraform-ingestion-contract.md) | Untrusted Terraform ingestion + evidence reproducibility contracts | Accepted, extends 0002 |
| [ADR-0028](0028-orchestration-ownership-boundary.md) | Step Functions/Lambda/AgentCore+LangGraph ownership boundary | Accepted, extends 0005/0008 |
| [ADR-0029](0029-cognito-otp-and-guest-caching.md) | Cognito OTP correction + cached guest report | Auth-method portion superseded by 0044; guest-caching principle carried forward into 0044 |
| [ADR-0030](0030-rate-limiting-reframed.md) | Rate limiting reframed as target + layered controls | Accepted, supersedes 0011 (framing) |
| [ADR-0031](0031-per-field-missing-data-policy.md) | Per-field missing-data policy (not one blanket default) | Accepted, supersedes 0012 |
| [ADR-0032](0032-ui-vertical-slice-milestones.md) | UI vertical-slice milestones, not a % target | Accepted, extends 0013 |
| [ADR-0033](0033-hugging-face-path-corrected.md) | Corrected Hugging Face implementation path (Guardrails, not Custom Model Import for Prompt Guard 2) | Accepted, supersedes 0014 (implementation) |
| [ADR-0034](0034-aurora-cost-comparison-corrected.md) | Corrected Aurora Serverless v2 cost comparison | Accepted, supersedes 0017 (reasoning) |
| [ADR-0035](0035-titan-baseline-not-cost-locked.md) | Titan V2 as baseline candidate, formal eval deferred | Accepted, supersedes 0019 (framing) |
| [ADR-0036](0036-structure-aware-chunking-baseline.md) | Structure-aware chunking baseline, richer citation metadata | Accepted, extends 0020 |
| [ADR-0037](0037-admin-owner-only.md) | Admin role owner-only; scoped reviewer role for invited reviewers (later) | Owner-only admin principle carried into 0044 (as pre-shared credential, not RBAC role); reviewer role cut by 0044 |
| [ADR-0038](0038-prompt-injection-architectural-boundaries.md) | Prompt-injection defense — architectural boundaries added | Accepted, extends 0022 |
| [ADR-0039](0039-base-report-field-completeness.md) | Base report field completeness + versioned "go deeper" snapshots | Accepted, extends 0023 |
| [ADR-0040](0040-budget-as-target-real-cost-reporting.md) | Budget as target/alert threshold; real measured cost always reported | Accepted, supersedes 0024 (framing) |
| [ADR-0041](0041-threat-modeling-methodology.md) | STRIDE primary + OWASP LLM Top 10 overlay + NIST AI RMF appendix | Accepted — completes the threat-modeling research item |
| [ADR-0042](0042-minor-amendments-batch.md) | Minor amendments: 0003, 0004, 0006, 0007, 0009, 0015, 0016, 0018, 0025 | Accepted, extends listed ADRs |
| [ADR-0043](0043-auth-method-simplified-password-plus-email-code.md) | Auth method simplified — email/password primary, emailed auth code as second factor; passkeys deferred past v1 | Superseded by 0044 |
| [ADR-0044](0044-no-user-accounts-admin-pre-shared-credential.md) | No user accounts — single admin pre-shared credential; guest mode fully static | Accepted, supersedes 0010, 0018, 0029 (method), 0043; cuts 0037's reviewer role |
| [ADR-0045](0045-archive-path-direct-upload.md) | archive_path resolved via direct S3 upload (presigned POST); GitHub-fetch deferred with a full hardening writeup | Accepted |
| [ADR-0046](0046-public-reviews-and-grounded-chat.md) | Public anonymous reviews + grounded report chat, quota-limited (Turnstile, per-IP-key, per-review, global daily cap); staged injection defenses with tests; no email | Accepted, supersedes 0044 guest-static |
| [ADR-0047](0047-landing-page-and-frontend-quality-gates.md) | Landing page = design option A above the review flow; full form shown, submitting owner-only (admin key) until public submissions open (ADR-0046 Phase 3); phone/contrast checks + Lighthouse CI gates | Accepted |
| [ADR-0048](0048-trivy-scanner-in-the-review-pipeline.md) | Trivy as the deterministic core in its own boxed-in Scan Lambda (layer, pinned + checksum, size alarm); own rules rebuilt as gap-filler/fallback; resource names capped; Trivy scan of our infra in CI + pre-commit | Accepted |
| [ADR-0049](0049-resource-summary-for-reasoning.md) | Reason gets a sanitized resource summary (allowlisted settings, typed or 32-char identifier values, cleaned names, no comments/tags/policies) so it stops guessing about the configuration | Accepted, extends 0038 |
| [ADR-0050](0050-grounded-chat-build.md) | Report chat built as one Lambda → Bedrock call per question: aliased review context + ADR-0049 summary + 3 WAF chunks + server-loaded history; strict tool output with server-verified citations, fixed refusals, canary; admin-only until public submissions open (ADR-0046 Phase 3); 5 questions/review, daily $ cap in one DynamoDB transaction; suggested answers on first click; Haiku 4.5 default pending the paid eval (amended 2026-10-17: Sonnet 4.6) | Accepted, implements 0046 §3–§6 |
| [ADR-0051](0051-stakeholder-costs.md) | Stakeholder view: plain-language cards and a budget summary; every dollar from a dated us-east-1 price table in code, sized from the Terraform; usage and unlisted sizes shown unpriced; the model only names price-table items and a plain block stating a price is dropped; cost of not fixing cites IBM/Sophos 2026 or gives a method | Accepted, extends 0039, 0049 |
