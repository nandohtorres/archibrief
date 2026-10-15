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
pipeline — Ingest → Scan (Trivy) → RuleEngine → PreflightGate → Retrieve → Reason →
Validate → Audit → Finalize, orchestrated by a real AWS Step Functions
state machine — has completed a real `SUCCEEDED` execution end to end
against the deployed AWS account, including a real human-in-the-loop
clarification pause/resume. Not yet open to the public: every
state-changing route sits behind a single pre-shared admin credential
(ADR-0044) — there are no user accounts, by design.

## What's real right now

- **Backend**: Python Lambda handlers, the LangGraph/Bedrock AgentCore
  reasoning subworkflow, the `Finding` pydantic model, a deterministic
  layer of Trivy's trusted checks plus ArchiBrief's own rules (ADR-0048),
  a sanitized resource summary so the model reasons from the real
  settings without seeing raw Terraform (ADR-0049), and every Terraform
  module are implemented,
  deployed, and have produced a real finding set against a real
  submitted Terraform repo. Backend test suite (`pytest`, no AWS
  credentials required — AWS calls go through moto or stubbed
  adapters): 398 passing, including an adversarial trap suite that
  runs with and without Trivy. 4 of them check the real
  ingested corpus and skip when `backend/corpus/data/` (gitignored) is
  absent.
- **RAG knowledge base**: AWS Well-Architected Framework + security
  best-practice sources normalized, chunked, embedded via Titan V2, and
  indexed in S3 Vectors; a deterministic lexical companion index covers
  exact-identifier lookups (CIS/SEC control IDs, etc.).
- **Frontend**: Next.js app, statically exported and served from S3 +
  CloudFront. A landing page with a one-click public sample review
  (`GET /demo`; ADR-0047), a real submission flow, live per-stage progress tracking
  (generic macro labels only — internal pipeline stage names are never
  exposed to the client), a real yes/no + multi-select clarification UI
  for human-in-the-loop pauses, three one-click quick-test presets
  (`detailed`/`medium`/`loose` severity), and a "go deeper" per-finding
  re-analysis action. 33 frontend unit tests (Vitest) and 29 Playwright
  E2E tests against a mocked network (never real AWS): the fixture path,
  the admin-gated submit → report → "go deeper" path and admin-key
  handling, the landing page and sample review, and phone-width (390px)
  and WCAG AA contrast checks in light and dark. `npm run lighthouse`
  scores the public build with Lighthouse CI (accessibility ≥ 95 and
  best practices ≥ 90 enforced).
- **Security**: Bedrock Guardrails gates every path into the model
  (ingest, and again before reasoning). The model itself has no AWS
  credentials and no tool-calling surface beyond a schema-validated
  `emit_findings` call; the AgentCore *runtime* that hosts the agent
  code does have an IAM role, limited to read/invoke actions (Bedrock
  InvokeModel/ApplyGuardrail, S3 Vectors query, `s3:GetObject` on its
  own code-artifact bucket, logs) with nothing mutating. Every emitted finding is independently
  re-verified server-side (citations must resolve to a real retrieved
  chunk). Prompt-injection regression tests for the reasoning node run
  in CI against a stubbed model (no Bedrock calls).
  Full sanitization audit (XSS/command-injection/DB-injection/path-
  traversal/prompt-injection) completed 2026-10-13 — see
  `docs/adr/Work-Project-ADR-0038...` and the issues log for the full
  writeup.
- **CI**: `ci.yml` runs real `ruff`/`pytest`/Vitest/Playwright/
  `terraform fmt`/`tflint`/`gitleaks` on every push and PR — currently
  advisory, not a
  blocking merge gate (GitHub branch protection requires either a public
  repo or GitHub Pro; this repo is currently private).

## Known gaps before opening this up publicly

Tracked in detail in the Leonardo vault's Build Plan/Issues Log
(private, not duplicated here). As of 2026-10-14:

**Closed since the last pass** — per-Lambda IAM roles (audited
against the live roles 2026-10-13; a 2026-10-15 review still found
Audit and Finalize sharing one over-broad policy, now split in code and
pending apply), the kill switch (live-triggered against the real deployment,
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

1. **Trap suite coverage**:
   `tests/backend/traps/` runs adversarial Terraform through the real
   parser, Trivy and the rule engine. Its first run (2026-10-15) found
   the engine missed all 14 sneaky-but-dangerous configs and flagged 3
   of 4 safe ones; with Trivy plus rebuilt rules (ADR-0048) it now
   catches 14/14 with no false positives, with and without Trivy. The
   suite only proves the patterns it contains. The Scan step is
   deployed and was proven in a live end-to-end review on 2026-10-15.
2. The model-side trap briefs (`backend/agent/trap_eval.py`) and the
   retrieval-evaluation harness call real Bedrock, so they are run
   manually with explicit approval, not in CI.
3. "Go deeper" is synchronous behind the HTTP API's 30-second limit:
   the agent call is capped at ~24 s and returns a clean timeout
   error beyond that. Moving it to an async job is the follow-up if
   real runs need longer.
4. Full CI gating (branch-protection required status checks) — blocked
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
  /lambdas       — bounded, stateless Lambda work: ingest, scan,
                   rule_engine, store_clarification_token, clarify_review,
                   validate, audit, finalize, mark_review_failed,
                   deeper_review, get_review, get_demo, admin_authorizer,
                   create_upload
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

## Building and deploying

From the repo root, then `terraform plan` and `terraform apply` in
`infra/environments/dev`:

```
python scripts/package_lambdas.py      # every Lambda zip
python scripts/build_trivy_layer.py    # Trivy layer (ADR-0048)
```

Builds are reproducible. Third-party versions are pinned in
`scripts/lambda_constraints.txt`, and the build fails if pip bundles
anything not pinned there. Zips are written with fixed timestamps, so a
plan only shows Lambdas whose code or dependencies really changed. To
upgrade a dependency, change its pin, rebuild, and run the backend tests.

## Stack (locked, see ADRs for reasoning)

Python (backend) · Next.js/TypeScript (frontend) · Terraform (infra) ·
AWS Lambda + Step Functions + API Gateway · DynamoDB · S3 + S3 Vectors ·
Bedrock (Claude + Titan V2 + Guardrails) · LangGraph on Bedrock AgentCore
· S3 + CloudFront (frontend hosting). No user accounts — a single
pre-shared admin credential gates the live pipeline; the one guest/demo
route is fully static and needs no auth (ADR-0044).

## License

[MIT](LICENSE)
