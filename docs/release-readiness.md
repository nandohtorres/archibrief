# Local candidate and release handoff

This is a source/verification checkpoint, not a declaration that every roadmap
gate or the live application is complete. Work is isolated on
`codex/report-contract-redesign`; the bounded checkpoint remains
`codex/portfolio-trust-fixes` / `checkpoint/bounded-fixes-2026-10-23`.
Nothing in this session was pushed, deployed or evaluated with a real model.

## Implemented locally

- Demo corrections and saved-answer warnings travel with exports; direct links,
  browser recovery and clearer failure states have regression coverage.
- Risk/action assessments are independent of evidence type; rejected-output
  quality counters survive publication.
- Original S3 evidence plus durable children feed report, diagrams and chat.
  Deeper reviews use bounded background jobs, atomic outcomes and reload recovery.
- Corrected semantic criteria preserve the frozen baseline. Six guarded runners
  distinguish free contracts, model components and integrated local application
  evaluation. Raw failures stay counted; source/case/schema/corpus/configuration
  fingerprints and call/generation controls make later runs reviewable.
- [Bounded architecture coverage](terraform-coverage.md) supplies placement,
  routing, retention, backup-selection and entry-path observations with explicit
  unknowns and limits. It does not implement all Terraform or verify deployment.
- Startup logs survive browser-server build failure. CI uploads them alongside
  traces/reports. Static builds emit `build-info.json` with the actual exported
  index hash, a declared revision when supplied and an explicit unverified backend.
- The [retention example](examples/retention-remediation/README.md) is a measured
  static before/after comparison, not a model benchmark.

The current candidate's exact checks are recorded in the session/review ledgers.
The final full backend run passed 1,234 tests / 5 skipped / 26 coverage-gap cases
deselected, including conservative noncurrent-block controls. The full browser
suite passed 75; frontend unit tests passed 83; tooling tests passed four. One
real static export verified the new postbuild stamp against its index bytes.
Backend Ruff lint/format, continuation Python lint/format, ESLint, TypeScript,
Prettier and staged Gitleaks checks passed. Broader optional tests/scripts Ruff
scans also expose pre-existing style debt outside CI's backend-only scope; no
unrelated formatting sweep was made. Local Python was 3.14.3 with isolated pinned
LangGraph dependencies; CI's Python 3.12 run remains pending publication.

The separate frozen coverage selection is 18 pass / 8 fail, not a hidden clean
score. [Coverage reconciliation](terraform-coverage.md) explains its four remaining
expectations and the two separate lexical false-positive corrections. No frozen
key, fixture, saved score, historical model input or demo result was rewritten.

## Public read-only observations, 2026-10-24

The landing page returned HTTP 200 and contains the GitHub source link. Its
last-modified header was 2026-10-23 18:49:17 GMT; downloaded HTML SHA256 was
`7655e3a7800d22aac45a4ee53dc33c015adae87be437bfc81d2471b459f2810f`.
GitHub master was `4fb3ac42cf5ade8711f2adad814b89e6b3a54791` (PR #28).
No redesign PR was found for this branch during the check. These observations
do not establish which full revision is deployed, public submission behavior,
model quality, retention, IAM or successful end-to-end reviews.

## Remaining gates

| Gate | Needed before claiming completion |
|---|---|
| Peer review/publication | Publish the two explicitly approved branches and draft reviews; have Claude review the full history and choose changes. Pushes require Fernando's specific instruction. |
| Terraform/deployment | Rebuild affected Lambda/AgentCore packages; validate locked provider schemas and a fresh plan; review IAM/KMS, workflow timing and migration; deploy only after approval. Earlier HCL parse/fmt/Trivy checks are not a fresh plan. |
| Paid quality | Approve account/SDK Region/model/guards, exact cases and call/output scope plus an actual spending allowance. Limits do not enforce a verified dollar ceiling. Run a small batch and inspect all attempts before extending it. |
| Semantic adjudication | Review correctness, source support, scope and recommendations across retained/rejected output. Keyword matches, quote integrity and successful contracts are not model accuracy. |
| Live integration | Verify capabilities, Turnstile, CORS/WAF/default-endpoint boundaries, immutable uploads, concurrency/idempotency, clarification, partial/all-rejected output, deeper recovery, chat, kill switch and callbacks against deployed services. |
| Privacy/retention | Inventory current objects/history/logs/PITR/backups, verify actual retention and contact/processors, and reconcile public text. Preserve data before destructive retention changes. |
| Portfolio evidence | Capture the approved deployed revision and fresh screenshots/performance. Finish human accessibility checks and the paired-workload model demonstration; historical Lighthouse numbers remain historical. |
| Money/effort UI | Explicitly deferred by Fernando. Prices, numeric effort and aggregation were left unchanged. New qualitative findings do not receive invented price recipes. |

No rollout, paid smoke test, migration, notification or retention change is
authorized merely by this document. The next concrete step is publishing the
reviewable branches after the specific push instruction, then independent review.

## Build identity and failure diagnostics

Both `npm run build` and `npm run build:e2e` generate `build-info.json` after the
static export. `ARCHIBRIEF_BUILD_REVISION` may name the approved commit; GitHub
Actions otherwise supplies `GITHUB_SHA`. Unavailable/invalid revisions stay null,
with `revision_source: unrecorded`. Operator-supplied identity is not an attestation.
The index SHA256 can be compared with downloaded HTML after an approved deployment;
backend versions/permissions require separate verification. No arbitrary environment
values enter the stamp.

Per-variant build logs are written while compilation runs under ignored
`frontend/e2e-build-logs/`. A timeout can therefore leave diagnostic evidence even
before Playwright creates its report. CI retains failure artifacts for seven days.
Local success does not diagnose the historical remote CI failure or replace the
next actual CI run. No blind timeout or production ranking change was made.
