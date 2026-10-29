# Release status

What is live, how a release ships, and what is still open. Updated
2026-10-29. The earlier local-candidate handoff (Codex branches, 2026-10-24)
is in git history; its branches were merged as PR #29 and later.

## Live

[archibrief.dev](https://archibrief.dev) is open to the public: anyone can
submit Terraform within the daily limits, open the three hand-checked demos,
go deeper on a finding, ask the report chat and share a read-only link.

| Part | Revision | How it got there |
|---|---|---|
| Frontend | `master` after PR #51 | Deployed automatically by `deploy-frontend.yml` after green CI (ADR-0055) |
| Backend (Lambdas, Step Functions, AgentCore runtime) | `master` after PR #51 | Owner applied the review-quality plan on 2026-10-28 (0 add / 13 change / 0 destroy) |
| Open, not deployed | PR #52: streamed model call, rules-only fallback, brief hardening, risk-ordered summary cap | Waiting for merge, then package build and plan |

## Shipping a release

- **Frontend:** merge to `master`. CD publishes the exact CI-tested revision
  and checks the live build stamp; a daily GET-only smoke watches it. If two
  merges land close together, rerun the workflow on `master` afterwards so
  the newest revision is the one deployed.
- **Backend:** from the repository root, build the packages, then plan and
  apply in `infra/environments/dev`:

  ```text
  backend\.venv\Scripts\python.exe scripts\package_lambdas.py
  backend\.venv\Scripts\python.exe backend\agent\build_runtime_package.py
  terraform plan "-out=tmp/<name>.tfplan"
  terraform apply tmp/<name>.tfplan
  ```

  The owner reviews every plan and runs the apply. CI never deploys the
  backend.

## Verification at this revision

Measured on the PR #52 branch (2026-10-29); CI ran the same suites green.

| Suite | Result |
|---|---|
| Backend, CI selection (`-m "not coverage_gap"`) | 1,272 passed, 1 skipped, 26 deselected |
| Adversarial suite | 249 passed, 8 failed: the documented coverage gaps ([FIX_REPORT](../tests/backend/adversarial/FIX_REPORT.md)) |
| Frontend unit | 89 passed in 16 files |
| Playwright | 78 passed |
| Deterministic traps | 60 passed |
| Lint and types | Ruff, ESLint, TypeScript, Prettier pass |

None of these measures live model quality. The live hard tests below do,
by hand.

## Live hard tests

Three Terraform submissions with planted issues and answer keys (kept
outside this repository): a 74-resource payments platform, a 69-resource telehealth platform with a
lying brief, and a 119-resource EU logistics platform with a data-residency
requirement and injection planted in the code. Results and the fixes they
drove are in [evaluation](evaluation.md#live-hard-tests).

## Open gates

| Gate | Status |
|---|---|
| Deploy PR #52 | Merge, build packages, plan, apply. Then rerun hard test 1 (timed out before) and run hard test 3. |
| Model blind spots | 30+ resource types with no settings or details, unevaluated modules, the 80-resource cap ([coverage](terraform-coverage.md)). Next fixes are chosen from hard test results. |
| Paid evaluations | The chat's paid trap and quality runs are still pending. Model trap briefs run by hand. |
| Semantic accuracy | Quote matching proves provenance, not support. Hard-test scoring is a manual judgment against answer keys. |
| Retention inventory | Verify actual retention against the [privacy page](https://archibrief.dev/privacy.html). |
| Portfolio evidence | Fresh screenshots and demo GIF (current ones predate the report header redesign and the clarify removal). |
| Lambda concurrency (T4) | Unreserved; the account's concurrency ceiling is too low to reserve. Accepted. |

No rollout, paid run or retention change is authorized by this document.

## Build identity and failure diagnostics

Both `npm run build` and `npm run build:e2e` generate `build-info.json` after the
static export. `ARCHIBRIEF_BUILD_REVISION` may name the approved commit; GitHub
Actions otherwise supplies `GITHUB_SHA`. Unavailable/invalid revisions stay null,
with `revision_source: unrecorded`. The index SHA256 can be compared with the
downloaded HTML; backend versions need separate verification. No arbitrary
environment values enter the stamp.

Per-variant build logs are written while compilation runs under ignored
`frontend/e2e-build-logs/`, so a timeout leaves diagnostic evidence before
Playwright creates its report. CI keeps failure artifacts for seven days.
