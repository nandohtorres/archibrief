---
title: "Work Project (ArchiBrief) — ADR Index"
type: index
tags: [index, project, work-project, adr, archibrief]
created: "2026-09-03"
updated: "2026-09-03"
status: active
---

# ArchiBrief — Architecture Decision Records

One short, atomic file per real decision — Context / Decision /
Consequences / Status, following the standard ADR format (Michael
Nygard's original convention; see
[joelparkerhenderson/architecture-decision-record](https://github.com/joelparkerhenderson/architecture-decision-record)
for reference). Each ADR is **immutable once accepted** — if a decision
later changes, a new ADR supersedes it and links back rather than editing
history in place.

**Full debate/reasoning for any of these lives in the project decision log** — this
folder intentionally stays terse; it doesn't restate the back-and-forth,
just the outcome and why. **Current-state summary lives in
the project spec**, which links here for the "why" instead of
repeating it.

These are meant to be portable into the actual code repo's `docs/adr/`
once the project is built, to show design thinking publicly.

## Decisions

| # | Decision | Status |
|---|---|---|
| [ADR-0001](Work-Project-ADR-0001-Product-Name-And-Framing.md) | Product name (ArchiBrief) and framing (not "audit") | Accepted |
| [ADR-0002](Work-Project-ADR-0002-Product-Mode-Review-Not-Generation.md) | Review-mode primary, not generate-from-scratch | Accepted |
| [ADR-0003](Work-Project-ADR-0003-Framework-Mapping-Hierarchy.md) | AWS WAF/CIS/NIST/Security+ mapping hierarchy | Accepted |
| [ADR-0004](Work-Project-ADR-0004-IaC-Tool-Terraform.md) | Terraform over CDK | Accepted |
| [ADR-0005](Work-Project-ADR-0005-Compute-Serverless.md) | Serverless (Lambda/Step Functions) over ECS/Kubernetes | Accepted |
| [ADR-0006](Work-Project-ADR-0006-LLM-Provider-Bedrock.md) | Bedrock-primary, provider-agnostic layer | Accepted |
| [ADR-0007](Work-Project-ADR-0007-Vector-Store-S3-Vectors.md) | AWS S3 Vectors over OpenSearch Serverless | Accepted |
| [ADR-0008](Work-Project-ADR-0008-Agent-Framework-LangGraph-AgentCore.md) | LangGraph on Bedrock AgentCore | Accepted |
| [ADR-0009](Work-Project-ADR-0009-Backend-Language-Python.md) | Python | Accepted |
| [ADR-0010](Work-Project-ADR-0010-Auth-And-Demo-Access.md) | Real accounts + rate-limited guest mode | Superseded by 0044 |
| [ADR-0011](Work-Project-ADR-0011-Rate-Limiting-Day-One.md) | Rate limiting/cost controls from day one | Accepted |
| [ADR-0012](Work-Project-ADR-0012-Agentic-Preflight-Gate.md) | Baseline-data pre-flight gate, not open chat loop | Accepted |
| [ADR-0013](Work-Project-ADR-0013-UI-Build-Sequencing.md) | UI built early/in parallel, not deferred to end | Accepted |
| [ADR-0014](Work-Project-ADR-0014-Hugging-Face-Capability.md) | Optional HF sub-task via Bedrock Custom Model Import; no self-training | Accepted |
| [ADR-0015](Work-Project-ADR-0015-Public-Repo-Secrets-Handling.md) | One real public repo, no dummy repo; standard secret hygiene | Accepted |
| [ADR-0016](Work-Project-ADR-0016-Frontend-Framework-NextJS.md) | Frontend framework — Next.js | Accepted |
| [ADR-0017](Work-Project-ADR-0017-Application-Database-DynamoDB.md) | Application database — DynamoDB | Accepted |
| [ADR-0018](Work-Project-ADR-0018-Auth-Provider-Cognito.md) | Auth provider — Amazon Cognito | Superseded by 0044 |
| [ADR-0019](Work-Project-ADR-0019-Embedding-Model-Titan.md) | Embedding model — Titan V2 | Accepted |
| [ADR-0020](Work-Project-ADR-0020-RAG-Ingestion-Chunking.md) | RAG ingestion/chunking strategy | Accepted |
| [ADR-0021](Work-Project-ADR-0021-IAM-Model-And-App-RBAC.md) | IAM model + application-level RBAC (admin role) | AWS IAM portion stands; app-RBAC portion superseded by 0044 |
| [ADR-0022](Work-Project-ADR-0022-Prompt-Injection-Defense.md) | Prompt-injection defense architecture | Accepted |
| [ADR-0023](Work-Project-ADR-0023-Evaluation-Depth-Strategy.md) | Evaluation-depth strategy — lightweight first pass | Accepted, provisional |
| [ADR-0024](Work-Project-ADR-0024-Budget-Ceiling.md) | Budget ceiling — $50/month target | Accepted |
| [ADR-0025](Work-Project-ADR-0025-Diagram-Tooling-Interim.md) | Diagram tooling — mingrammer/diagrams (interim) | Accepted |
| [ADR-0026](Work-Project-ADR-0026-Documentation-Structure.md) | Documentation structure — Journal + Spec + Build Plan + ADRs | Accepted |
| [ADR-0027](Work-Project-ADR-0027-Untrusted-Terraform-Ingestion-Contract.md) | Untrusted Terraform ingestion + evidence reproducibility contracts | Accepted, extends 0002 |
| [ADR-0028](Work-Project-ADR-0028-Orchestration-Ownership-Boundary.md) | Step Functions/Lambda/AgentCore+LangGraph ownership boundary | Accepted, extends 0005/0008 |
| [ADR-0029](Work-Project-ADR-0029-Cognito-OTP-And-Guest-Caching.md) | Cognito OTP correction + cached guest report | Auth-method portion superseded by 0044; guest-caching principle carried forward into 0044 |
| [ADR-0030](Work-Project-ADR-0030-Rate-Limiting-Reframed.md) | Rate limiting reframed as target + layered controls | Accepted, supersedes 0011 (framing) |
| [ADR-0031](Work-Project-ADR-0031-Per-Field-Missing-Data-Policy.md) | Per-field missing-data policy (not one blanket default) | Accepted, supersedes 0012 |
| [ADR-0032](Work-Project-ADR-0032-UI-Vertical-Slice-Milestones.md) | UI vertical-slice milestones, not a % target | Accepted, extends 0013 |
| [ADR-0033](Work-Project-ADR-0033-Hugging-Face-Path-Corrected.md) | Corrected Hugging Face implementation path (Guardrails, not Custom Model Import for Prompt Guard 2) | Accepted, supersedes 0014 (implementation) |
| [ADR-0034](Work-Project-ADR-0034-Aurora-Cost-Comparison-Corrected.md) | Corrected Aurora Serverless v2 cost comparison | Accepted, supersedes 0017 (reasoning) |
| [ADR-0035](Work-Project-ADR-0035-Titan-Baseline-Not-Cost-Locked.md) | Titan V2 as baseline candidate, formal eval deferred | Accepted, supersedes 0019 (framing) |
| [ADR-0036](Work-Project-ADR-0036-Structure-Aware-Chunking-Baseline.md) | Structure-aware chunking baseline, richer citation metadata | Accepted, extends 0020 |
| [ADR-0037](Work-Project-ADR-0037-Admin-Fernando-Only.md) | Admin role owner-only; scoped reviewer role for invited reviewers (later) | Admin-Fernando-only principle carried into 0044 (as pre-shared credential, not RBAC role); reviewer role cut by 0044 |
| [ADR-0038](Work-Project-ADR-0038-Prompt-Injection-Architectural-Boundaries.md) | Prompt-injection defense — architectural boundaries added | Accepted, extends 0022 |
| [ADR-0039](Work-Project-ADR-0039-Base-Report-Field-Completeness.md) | Base report field completeness + versioned "go deeper" snapshots | Accepted, extends 0023 |
| [ADR-0040](Work-Project-ADR-0040-Budget-As-Target-Real-Cost-Reporting.md) | Budget as target/alert threshold; real measured cost always reported | Accepted, supersedes 0024 (framing) |
| [ADR-0041](Work-Project-ADR-0041-Threat-Modeling-Methodology.md) | STRIDE primary + OWASP LLM Top 10 overlay + NIST AI RMF appendix | Accepted — resolves W5 |
| [ADR-0042](Work-Project-ADR-0042-Minor-Amendments-Batch.md) | Minor amendments: 0003, 0004, 0006, 0007, 0009, 0015, 0016, 0018, 0025 | Accepted, extends listed ADRs |
| [ADR-0043](Work-Project-ADR-0043-Auth-Method-Simplified-Password-Plus-Email-Code.md) | Auth method simplified — email/password primary, emailed auth code as second factor; passkeys deferred past v1 | Superseded by 0044 |
| [ADR-0044](Work-Project-ADR-0044-No-User-Accounts-Admin-Pre-Shared-Credential.md) | No user accounts — single admin pre-shared credential; guest mode fully static | Accepted, supersedes 0010, 0018, 0029 (method), 0043; cuts 0037's reviewer role |
| [ADR-0045](Work-Project-ADR-0045-Archive-Path-Direct-Upload.md) | archive_path resolved via direct S3 upload (presigned POST); GitHub-fetch deferred with a full hardening writeup | Accepted |
| [ADR-0046](Work-Project-ADR-0046-Public-Reviews-and-Grounded-Chat.md) | Public anonymous reviews + grounded report chat, quota-limited (Turnstile, per-IP-key, per-review, global daily cap); staged injection defenses with tests; no email | Accepted, supersedes 0044 guest-static |
