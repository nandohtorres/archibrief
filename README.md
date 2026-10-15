# ArchiBrief

[![CI](https://github.com/nandohtorres/archibrief/actions/workflows/ci.yml/badge.svg)](https://github.com/nandohtorres/archibrief/actions/workflows/ci.yml)

<!-- Badge note: GitHub Actions badges don't render for unauthenticated
viewers on a private repo - this will show broken/blank until the repo
actually goes public. Correct and will work automatically once it is;
nothing more to do here at that point. -->

A secure AWS architecture reviewer: submit a bounded Terraform repo +
workload brief, get back typed, cited, confidence-scored findings —
evaluated via deterministic rule checks plus RAG-grounded LLM reasoning
against the AWS Well-Architected Framework and security best practices.

**Status: live, real deployment, admin-gated (2026-10-13).** The full
pipeline — Ingest → RuleEngine → PreflightGate → Retrieve → Reason →
Validate → Audit → Finalize, orchestrated by a real AWS Step Functions
state machine — has completed a real `SUCCEEDED` execution end to end
against the deployed AWS account, including a real human-in-the-loop
clarification pause/resume. Not yet open to the public: every
state-changing route sits behind a single pre-shared admin credential
(ADR-0044) — there are no user accounts, by design.

## What's real right now

- **Backend**: Python Lambda handlers, the LangGraph/Bedrock AgentCore
  reasoning subworkflow, the `Finding` pydantic model, a 16-scenario
  deterministic RuleEngine, and every Terraform module are implemented,
  deployed, and have produced a real finding set against a real
  submitted Terraform repo. Backend test suite: 237 passing (`pytest`,
  no AWS credentials required — AWS calls go through adapters
  mocked/stubbed in tests).
- **RAG knowledge base**: AWS Well-Architected Framework + security
  best-practice sources normalized, chunked, embedded via Titan V2, and
  indexed in S3 Vectors; a deterministic lexical companion index covers
  exact-identifier lookups (CIS/SEC control IDs, etc.).
- **Frontend**: Next.js app, statically exported and served from S3 +
  CloudFront. Real submission flow, live per-stage progress tracking
  (generic macro labels only — internal pipeline stage names are never
  exposed to the client), a real yes/no + multi-select clarification UI
  for human-in-the-loop pauses, three one-click quick-test presets
  (`detailed`/`medium`/`loose` severity), and a "go deeper" per-finding
  re-analysis action. 16 passing frontend unit tests (Vitest).
- **Security**: Bedrock Guardrails gates every path into the model
  (ingest, and again before reasoning); the model has no AWS credentials
  and no tool-calling surface beyond a schema-validated `emit_findings`
  call; every emitted finding is independently re-verified server-side
  (citations must resolve to a real retrieved chunk). A real adversarial
  prompt-injection regression suite exists and runs in CI on every push.
  Full sanitization audit (XSS/command-injection/DB-injection/path-
  traversal/prompt-injection) completed 2026-10-13 — see
  `docs/adr/Work-Project-ADR-0038...` and the issues log for the full
  writeup.
- **CI**: `ci.yml` runs real `ruff`/`pytest`/Vitest/`terraform fmt`/
  `tflint`/`gitleaks` on every push and PR — currently advisory, not a
  blocking merge gate (GitHub branch protection requires either a public
  repo or GitHub Pro; this repo is currently private).

## Known gaps before opening this up publicly

Tracked in detail in the Leonardo vault's Build Plan/Issues Log
(private, not duplicated here). As of 2026-10-14:

**Closed since the last pass** — per-Lambda least-privilege IAM
(audited directly against the live roles, no over-permissioning
found), the kill switch (live-triggered against the real deployment,
confirmed zero paid work runs while active), `GET /demo` rate
limiting (now an isolated throttle bucket, separate from the
admin-gated routes'), the Titan-vs-Cohere embedding comparison
(ADR-0035 — Titan V2 stays; Cohere scored lower and hits an
undocumented 2048-character input limit), the chunking-size comparison
(ADR-0036 — 512-token chunking stays), a real measured AWS cost figure
(tracked in the private Work-Project-Cost-Log), and the IAM
permission-set size ceiling (split into 5 logically-grouped
customer-managed policies, applied and verified live).

**Still genuinely open:**

1. Frontend and E2E test coverage is thin — a few Vitest unit tests
   exist, but no Playwright coverage of the real critical path yet
   (submit review → view findings → "go deeper"; guest/demo report
   view).
2. The adversarial regression suite and the retrieval-evaluation
   harness are run manually, not wired into CI as automated,
   re-runnable checks yet.
3. Full CI gating (branch-protection required status checks) — blocked
   on either making this repo public or a GitHub Pro upgrade; every
   test suite described above already runs on every push regardless,
   this only affects whether a failing check can block a merge.

## Architecture

Full system diagram, a step-by-step walkthrough of the review
pipeline, and the reasoning behind Step Functions vs. AgentCore's
division of responsibility: see [`docs/architecture.md`](docs/architecture.md).
A STRIDE/OWASP-LLM threat model against the same real deployment is at
[`docs/threat-model.md`](docs/threat-model.md).

## Design documents (source of truth, not duplicated here)

Full spec, system design, ADRs, build plan, and issues log live in the
Leonardo vault, not this repo, while the project is privately iterated
on:

- **Spec** — what/why, current locked scope.
- **System Design** — data models, API contracts, orchestration topology.
- **Build Plan** — ordered implementation steps and their real status.
- **Issues Log** — real bugs found during the build, root cause, and fix
  — kept as evidence of engineering judgment, not just a changelog.
- **ADRs** — copied into `docs/adr/` here for public-repo visibility (one
  atomic decision record per file, immutable once accepted).

## Structure

```
/infra          — Terraform modules (API Gateway, Step Functions/Lambda,
                   DynamoDB, S3, S3 Vectors, AgentCore Runtime, frontend
                   hosting, kill switch, cost controls, IAM), one module
                   per major component
/backend
  /lambdas       — bounded, stateless Lambda work: ingest, rule_engine,
                   store_clarification_token, clarify_review, validate,
                   audit, finalize, deeper_review, get_review, get_demo,
                   admin_authorizer, create_upload
  /agent         — the one LangGraph/AgentCore reasoning subworkflow:
                   /nodes (preflight, retrieve, reason) + graph.py. NOT
                   Lambda functions — Guardrails/"classify" runs inline
                   at ingest and again before reason, not as its own node
  /corpus        — RAG corpus build pipeline: normalize, chunk, embed,
                   lexical index, retrieval evaluation harness
  /shared        — pydantic models, shared AWS clients, report assembly
/frontend        — Next.js app (static export, served from S3/CloudFront)
/tests           — mirrors /backend and /frontend
/docs/adr        — copy of the vault's Work-Project-ADR/ folder
```

## Stack (locked, see ADRs for reasoning)

Python (backend) · Next.js/TypeScript (frontend) · Terraform (infra) ·
AWS Lambda + Step Functions + API Gateway · DynamoDB · S3 + S3 Vectors ·
Bedrock (Claude + Titan V2 + Guardrails) · LangGraph on Bedrock AgentCore
· S3 + CloudFront (frontend hosting). No user accounts — a single
pre-shared admin credential gates the live pipeline; the one guest/demo
route is fully static and needs no auth (ADR-0044).

## License

[MIT](LICENSE)
