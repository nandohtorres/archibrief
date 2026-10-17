# ArchiBrief

**Context-aware architecture review with receipts.**

ArchiBrief combines static Terraform checks with a workload brief and retrieved AWS guidance. A public bucket means something different for public records than for cardholder data; availability advice needs a traffic profile and a target. The report puts the observed configuration, risk, recommendation, alternatives, and confidence alongside its evidence so a reviewer can challenge the result.

## Status

**Deployed and admin-gated; public self-service is not open yet.** Anyone can open three finished demo reviews of real public Terraform (a security firm's breach lab, a Medicare data platform, and FEC databases). They load from saved files, so opening one starts no model run. Each finding was checked by hand against the code, and the ones the model got wrong carry a visible reviewer note ([docs/demos.md](docs/demos.md)).

**Report chat is live for the owner.** Questions about one finished review get cited answers checked server-side against that review ([docs/chat.md](docs/chat.md), [ADR-0050](docs/adr/Work-Project-ADR-0050-Grounded-Chat-Build.md)). It runs on Claude Sonnet 4.6 behind Guardrails, quotas and a hard daily spend cap. The demos' suggested questions were answered once and are served free. The paid chat evaluation is still pending.

## How it works

1. Upload a bounded Terraform archive and describe the workload. Ingestion validates the archive and parses HCL statically; it does not run Terraform, providers, or provisioners.
2. Trivy supplies selected trusted checks, augmented by ArchiBrief's deterministic rules. If scanning is unavailable, rules still run and scanner status is recorded.
3. Preflight requests missing context or records explicit defaults. Step Functions owns the review lifecycle and clarification pause/resume.
4. A LangGraph subworkflow on Bedrock AgentCore retrieves AWS guidance and reasons over the brief, rule findings, and a sanitized resource summary. The reasoning model does not receive raw Terraform.
5. Server-side validation checks typed findings and citation provenance before audit/finalization. A model finding's quote must match a retrieved chunk. Deterministic findings use configuration evidence rather than model citations.

The frontend exposes progress, clarification, findings, a stakeholder view of the same evidence, per-finding “go deeper,” report chat, and an HTML report download that includes the conversation. See [architecture](docs/architecture.md), [threat model](docs/threat-model.md), [evaluation](docs/evaluation.md), and [Trivy comparison](docs/comparison.md).

## What the receipts establish—and their limits

- A matching citation proves that a passage exists in retrieved material; it does **not** prove the passage supports the conclusion. The saved breach report includes a weak attack-chain citation and an incorrect data-transfer cost claim; [the demo audit](docs/demos.md) records both.
- This is static review of the submitted slice, not inspection of deployed AWS resources, a complete dependency graph, a compliance certification, or a penetration test. Remote modules are neutralized before scanning.
- Counts, expressions, missing modules, and omitted settings limit what the model can observe. The demo audits found three such gaps (resource counts, backup plans, snapshot settings); each was fixed in the resource summary, and the FEC demo was re-run after the count fix.
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

Live at **[archibrief.dev](https://archibrief.dev)**: open any of the three demo reviews without an account.

![Opening a demo review: landing, demo cards, report, reviewer note, stakeholder view and chat](docs/screenshots/demo.gif)

| | |
|---|---|
| ![Landing page](docs/screenshots/01-landing.png) | ![Finished demo reviews and example architectures](docs/screenshots/02-demo-cards.png) |
| **Landing.** A second opinion on your Terraform, with the receipts. | **Try it.** Three finished reviews of real public Terraform, or start from an example. |
| ![A finding with a reviewer note](docs/screenshots/04-reviewer-note.png) | ![Stakeholder view with demo provenance](docs/screenshots/05-stakeholder.png) |
| **Evidence.** Each finding shows its evidence, confidence and source; the hand check's note marks one the model got wrong. | **Provenance.** Source, license and disclaimer, then the stakeholder view of the same evidence. |
| ![Report chat with cited answers](docs/screenshots/06-chat.png) | ![Phone layout, dark theme](docs/screenshots/07-phone.png) |
| **Chat.** Answers cite this review's findings or AWS guidance. | **Phone, dark theme.** |

## Repository map

`backend/lambdas/` contains pipeline and API handlers; `backend/agent/` contains reasoning and its evaluation harnesses; `backend/chat/` contains the built chat path; `backend/corpus/` builds and evaluates retrieval. `frontend/` is the static web app, `tests/` holds unit tests, and `docs/adr/` records decisions.

## License

[MIT](LICENSE). Demo archives carry their upstream license/provenance; see [docs/demos.md](docs/demos.md).
