# ArchiBrief

A secure AWS architecture reviewer: submit a bounded Terraform repo +
workload brief, get back typed, cited, confidence-scored findings —
evaluated via deterministic rule checks plus RAG-grounded LLM reasoning
against the AWS Well-Architected Framework and security best practices.

**Status: real backend/infra code, not yet deployed.** Backend Lambda
handlers, LangGraph agent nodes, the `Finding` pydantic model, the
16-scenario RuleEngine, and all Terraform modules are implemented and
covered by a passing `pytest` suite (33 tests, no AWS credentials
required — AWS calls go through adapters mocked/stubbed in tests). CI
(`ci.yml`) runs real `ruff`/`pytest`/`terraform fmt`/`tflint`/`gitleaks`
invocations, still advisory.

**Progress 2026-09-08:** a dedicated AWS account now exists (IAM Identity
Center, `AdminAccess` for bootstrap + a real least-privilege
`ArchiBriefDeploy` permission set for Terraform — see
`infra/environments/dev/deploy-role-policy.json`), and `terraform init`/
`terraform validate` have both been run for real against these modules
and passed (`.terraform.lock.hcl` now committed).

**Not yet done:** `terraform plan`/`apply` — the Lambda deployment
packages aren't built yet, and the SES/GitHub-OIDC/AgentCore Runtime ARN
values in `terraform.tfvars` are still placeholders, so `plan` is
expected to surface real errors on the Lambda resources until those
exist; the RAG knowledge-base corpus itself (curation/normalization/
embedding, Phase 2) isn't built or populated; the Next.js frontend
(`/frontend`) is still an empty scaffold; the adversarial regression
suite (ADR-0038) doesn't exist; nothing has been smoke-tested end to
end. Domain is `archibrief.dev` (registered 2026-09-08). See `docs/adr/`
for the full decision trail.

## Design documents (source of truth, not duplicated here)

Full spec, system design, ADRs, and build plan live in the
[Leonardo](../../Leonardo) vault, not this repo, while the project is in
active design:

- **Spec** — what/why, current locked scope.
- **System Design** — data models, API contracts, orchestration topology.
- **Build Plan** — ordered implementation steps.
- **ADRs** — copied into `docs/adr/` here for public-repo visibility (one
  atomic decision record per file, immutable once accepted).

## Structure

```
/infra          — Terraform modules (auth, API Gateway, Step Functions/
                   Lambda, DynamoDB, S3, S3 Vectors, IAM), one module per
                   major component
/backend
  /lambdas       — bounded, stateless Lambda work only: ingest,
                   rule_engine, validate, audit, finalize
  /agent         — the one LangGraph/AgentCore reasoning subworkflow:
                   /nodes (preflight, retrieve, reason) + graph.py.
                   NOT Lambda functions — Guardrails/"classify" runs
                   inline at ingest and again before reason, not as its
                   own node
  /shared        — pydantic models, shared AWS clients
/frontend        — Next.js app
/tests           — mirrors /backend and /frontend
/docs/adr        — copy of the vault's Work-Project-ADR/ folder
/docs/site       — local diagram/walkthrough of the full system + UX
```

## Stack (locked, see ADRs for reasoning)

Python (backend) · Next.js/TypeScript (frontend) · Terraform (infra) ·
AWS Lambda + Step Functions + API Gateway · DynamoDB · S3 + S3 Vectors ·
Bedrock (Claude + Titan V2 + Guardrails) · LangGraph on Bedrock AgentCore
· Cognito.
