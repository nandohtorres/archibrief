# ArchiBrief

**Context-aware architecture review with receipts.**

ArchiBrief combines static Terraform checks with a workload brief and retrieved AWS guidance. A public bucket means something different for public records than for cardholder data; availability advice needs a traffic profile and a target. The report puts the observed configuration, risk, recommendation, alternatives, and confidence alongside its evidence so a reviewer can challenge the result.

## Status

**The review pipeline is admin-gated. Public self-service is not ready.** The repository records completed deployed demo reviews in [docs/demos.md](docs/demos.md), with saved reports and exact source archives under `frontend/public/demos/`. Those records are historical evidence, not a fresh check of deployment health. The public sample is precomputed; opening it does not start a model review.

**Report chat is built, not deployed in this checkout's recorded status.** Its handlers, UI, mocked tests, and deployment steps are in [docs/chat.md](docs/chat.md) and [ADR-0050](docs/adr/Work-Project-ADR-0050-Grounded-Chat-Build.md). The paid chat evaluation and live smoke test remain pending there. Implemented chat controls are not proof that they protect the live service today.

## How it works

1. Upload a bounded Terraform archive and describe the workload. Ingestion validates the archive and parses HCL statically; it does not run Terraform, providers, or provisioners.
2. Trivy supplies selected trusted checks, augmented by ArchiBrief's deterministic rules. If scanning is unavailable, rules still run and scanner status is recorded.
3. Preflight requests missing context or records explicit defaults. Step Functions owns the review lifecycle and clarification pause/resume.
4. A LangGraph subworkflow on Bedrock AgentCore retrieves AWS guidance and reasons over the brief, rule findings, and a sanitized resource summary. The reasoning model does not receive raw Terraform.
5. Server-side validation checks typed findings and citation provenance before audit/finalization. A model finding's quote must match a retrieved chunk. Deterministic findings use configuration evidence rather than model citations.

The frontend exposes progress, clarification, findings, and per-finding “go deeper.” See [architecture](docs/architecture.md), [threat model](docs/threat-model.md), [evaluation](docs/evaluation.md), and [Trivy comparison](docs/comparison.md).

## What the receipts establish—and their limits

- A matching citation proves that a passage exists in retrieved material; it does **not** prove the passage supports the conclusion. The saved breach report includes a weak attack-chain citation and an incorrect data-transfer cost claim; [the demo audit](docs/demos.md) records both.
- This is static review of the submitted slice, not inspection of deployed AWS resources, a complete dependency graph, a compliance certification, or a penetration test. Remote modules are neutralized before scanning.
- Counts, expressions, missing modules, and omitted settings limit what the model can observe. The saved FEC report contains incorrect replica claims and is marked unpublished in the demo documentation, pending a rerun.
- Trap tests cover their fixtures. Mocked tests do not measure live model quality, production IAM correctness, or deployed accessibility.
- “Go deeper” is synchronous with a bounded agent timeout; long requests can fail.
- Anonymous admission, atomic quotas across paid paths, upload binding, secret scanning, retention enforcement, and a truthful privacy page remain public-launch work. A seven-day deletion guarantee is not established by this checkout.

## Stack

| Layer | Implementation |
|---|---|
| UI | Next.js, React, TypeScript; static export to S3/CloudFront |
| Orchestration | API Gateway HTTP API, Lambda, Step Functions |
| Static review | Python, python-hcl2, Trivy, custom deterministic rules |
| Reasoning | LangGraph on Bedrock AgentCore; Bedrock Claude, Guardrails |
| Retrieval | Titan V2 embeddings, S3 Vectors, lexical companion index |
| Storage | S3, DynamoDB |
| Infrastructure | Terraform modules in `infra/` |
| Verification | pytest/moto, Vitest, Playwright; `.github/workflows/ci.yml` |

## Local development

Backend dependencies and development extras are declared in `backend/pyproject.toml` (Python 3.12+). Frontend commands are in `frontend/package.json` (Node 20 or 22). With dependencies installed, from the repository root:

```text
python -m pytest tests/backend -q
cd frontend
npm ci
npm run dev
```

Without `NEXT_PUBLIC_API_BASE_URL`, the UI uses the local fixture path. Playwright builds separate fixture and mocked-API static sites; its API tests do not require AWS credentials. Live retrieval/model evaluation harnesses are paid operations and separate from these tests. See [evaluation](docs/evaluation.md) for evidence and reproducible commands.

## Screenshots

Screenshots are pending capture; these are placeholders, not rendered product images.

| Planned capture | What it should demonstrate |
|---|---|
| Landing and sample selection | Saved demo provenance and admin-only submission notice |
| Clarification | Explicit defaults and unanswered requirements |
| Report with expanded evidence | Configuration evidence, guidance quote, confidence and alternatives |
| Narrow viewport | Report reading and keyboard focus on a phone-width layout |

## Repository map

`backend/lambdas/` contains pipeline and API handlers; `backend/agent/` contains reasoning and its evaluation harnesses; `backend/chat/` contains the built chat path; `backend/corpus/` builds and evaluates retrieval. `frontend/` is the static web app, `tests/` holds unit tests, and `docs/adr/` records decisions.

## License

[MIT](LICENSE). Demo archives carry their upstream license/provenance; see [docs/demos.md](docs/demos.md).
