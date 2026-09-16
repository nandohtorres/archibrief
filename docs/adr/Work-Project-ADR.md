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

**Full debate/reasoning for any of these lives in [[Work-Project]]** — this
folder intentionally stays terse; it doesn't restate the back-and-forth,
just the outcome and why. **Current-state summary lives in
[[Work-Project-Spec]]**, which links here for the "why" instead of
repeating it.

These are meant to be portable into the actual code repo's `docs/adr/`
once the project is built, to show design thinking publicly.

## Decisions

| # | Decision | Status |
|---|---|---|
| [[Work-Project-ADR-0001-Product-Name-And-Framing]] | Product name (ArchiBrief) and framing (not "audit") | Accepted |
| [[Work-Project-ADR-0002-Product-Mode-Review-Not-Generation]] | Review-mode primary, not generate-from-scratch | Accepted |
| [[Work-Project-ADR-0003-Framework-Mapping-Hierarchy]] | AWS WAF/CIS/NIST/Security+ mapping hierarchy | Accepted |
| [[Work-Project-ADR-0004-IaC-Tool-Terraform]] | Terraform over CDK | Accepted |
| [[Work-Project-ADR-0005-Compute-Serverless]] | Serverless (Lambda/Step Functions) over ECS/Kubernetes | Accepted |
| [[Work-Project-ADR-0006-LLM-Provider-Bedrock]] | Bedrock-primary, provider-agnostic layer | Accepted |
| [[Work-Project-ADR-0007-Vector-Store-S3-Vectors]] | AWS S3 Vectors over OpenSearch Serverless | Accepted |
| [[Work-Project-ADR-0008-Agent-Framework-LangGraph-AgentCore]] | LangGraph on Bedrock AgentCore | Accepted |
| [[Work-Project-ADR-0009-Backend-Language-Python]] | Python | Accepted |
| [[Work-Project-ADR-0010-Auth-And-Demo-Access]] | Real accounts + rate-limited guest mode | Superseded by 0044 |
| [[Work-Project-ADR-0011-Rate-Limiting-Day-One]] | Rate limiting/cost controls from day one | Accepted |
| [[Work-Project-ADR-0012-Agentic-Preflight-Gate]] | Baseline-data pre-flight gate, not open chat loop | Accepted |
| [[Work-Project-ADR-0013-UI-Build-Sequencing]] | UI built early/in parallel, not deferred to end | Accepted |
| [[Work-Project-ADR-0014-Hugging-Face-Capability]] | Optional HF sub-task via Bedrock Custom Model Import; no self-training | Accepted |
| [[Work-Project-ADR-0015-Public-Repo-Secrets-Handling]] | One real public repo, no dummy repo; standard secret hygiene | Accepted |
| [[Work-Project-ADR-0016-Frontend-Framework-NextJS]] | Frontend framework — Next.js | Accepted |
| [[Work-Project-ADR-0017-Application-Database-DynamoDB]] | Application database — DynamoDB | Accepted |
| [[Work-Project-ADR-0018-Auth-Provider-Cognito]] | Auth provider — Amazon Cognito | Superseded by 0044 |
| [[Work-Project-ADR-0019-Embedding-Model-Titan]] | Embedding model — Titan V2 | Accepted |
| [[Work-Project-ADR-0020-RAG-Ingestion-Chunking]] | RAG ingestion/chunking strategy | Accepted |
| [[Work-Project-ADR-0021-IAM-Model-And-App-RBAC]] | IAM model + application-level RBAC (admin role) | AWS IAM portion stands; app-RBAC portion superseded by 0044 |
| [[Work-Project-ADR-0022-Prompt-Injection-Defense]] | Prompt-injection defense architecture | Accepted |
| [[Work-Project-ADR-0023-Evaluation-Depth-Strategy]] | Evaluation-depth strategy — lightweight first pass | Accepted, provisional |
| [[Work-Project-ADR-0024-Budget-Ceiling]] | Budget ceiling — $50/month target | Accepted |
| [[Work-Project-ADR-0025-Diagram-Tooling-Interim]] | Diagram tooling — mingrammer/diagrams (interim) | Accepted |
| [[Work-Project-ADR-0026-Documentation-Structure]] | Documentation structure — Journal + Spec + Build Plan + ADRs | Accepted |
| [[Work-Project-ADR-0027-Untrusted-Terraform-Ingestion-Contract]] | Untrusted Terraform ingestion + evidence reproducibility contracts | Accepted, extends 0002 |
| [[Work-Project-ADR-0028-Orchestration-Ownership-Boundary]] | Step Functions/Lambda/AgentCore+LangGraph ownership boundary | Accepted, extends 0005/0008 |
| [[Work-Project-ADR-0029-Cognito-OTP-And-Guest-Caching]] | Cognito OTP correction + cached guest report | Auth-method portion superseded by 0044; guest-caching principle carried forward into 0044 |
| [[Work-Project-ADR-0030-Rate-Limiting-Reframed]] | Rate limiting reframed as target + layered controls | Accepted, supersedes 0011 (framing) |
| [[Work-Project-ADR-0031-Per-Field-Missing-Data-Policy]] | Per-field missing-data policy (not one blanket default) | Accepted, supersedes 0012 |
| [[Work-Project-ADR-0032-UI-Vertical-Slice-Milestones]] | UI vertical-slice milestones, not a % target | Accepted, extends 0013 |
| [[Work-Project-ADR-0033-Hugging-Face-Path-Corrected]] | Corrected Hugging Face implementation path (Guardrails, not Custom Model Import for Prompt Guard 2) | Accepted, supersedes 0014 (implementation) |
| [[Work-Project-ADR-0034-Aurora-Cost-Comparison-Corrected]] | Corrected Aurora Serverless v2 cost comparison | Accepted, supersedes 0017 (reasoning) |
| [[Work-Project-ADR-0035-Titan-Baseline-Not-Cost-Locked]] | Titan V2 as baseline candidate, formal eval deferred | Accepted, supersedes 0019 (framing) |
| [[Work-Project-ADR-0036-Structure-Aware-Chunking-Baseline]] | Structure-aware chunking baseline, richer citation metadata | Accepted, extends 0020 |
| [[Work-Project-ADR-0037-Admin-Fernando-Only]] | Admin role Fernando-only; scoped reviewer role for recruiters (later) | Admin-Fernando-only principle carried into 0044 (as pre-shared credential, not RBAC role); reviewer role cut by 0044 |
| [[Work-Project-ADR-0038-Prompt-Injection-Architectural-Boundaries]] | Prompt-injection defense — architectural boundaries added | Accepted, extends 0022 |
| [[Work-Project-ADR-0039-Base-Report-Field-Completeness]] | Base report field completeness + versioned "go deeper" snapshots | Accepted, extends 0023 |
| [[Work-Project-ADR-0040-Budget-As-Target-Real-Cost-Reporting]] | Budget as target/alert threshold; real measured cost always reported | Accepted, supersedes 0024 (framing) |
| [[Work-Project-ADR-0041-Threat-Modeling-Methodology]] | STRIDE primary + OWASP LLM Top 10 overlay + NIST AI RMF appendix | Accepted — resolves W5 |
| [[Work-Project-ADR-0042-Minor-Amendments-Batch]] | Minor amendments: 0003, 0004, 0006, 0007, 0009, 0015, 0016, 0018, 0025 | Accepted, extends listed ADRs |
| [[Work-Project-ADR-0043-Auth-Method-Simplified-Password-Plus-Email-Code]] | Auth method simplified — email/password primary, emailed auth code as second factor; passkeys deferred past v1 | Superseded by 0044 |
| [[Work-Project-ADR-0044-No-User-Accounts-Admin-Pre-Shared-Credential]] | No user accounts — single admin pre-shared credential; guest mode fully static | Accepted, supersedes 0010, 0018, 0029 (method), 0043; cuts 0037's reviewer role |
