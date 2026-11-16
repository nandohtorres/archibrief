# Release status

> **2026-11-16 checkpoint:** PR #67's brief and PR #68's first accuracy repairs are released per the owner/Claude handoffs; local git verifies merge 613ab0c. Latest rules 091ee10, P3b 1a75227 and owner tools 0721c82 remain local candidates. Codex builds/freezes; Claude independently reviews/releases/evaluates. Do not treat historical pass counts below as release checks for those new SHAs. See [current status](current-status.md).

What is live, how a release ships, and what is still open. Live table and
release steps updated 2026-11-16; the verification section below is from
2026-10-29. The earlier local-candidate handoff (Codex branches, 2026-10-24)
is in git history; its branches were merged as PR #29 and later.

## Live

[archibrief.dev](https://archibrief.dev) is open to the public: anyone can
submit Terraform within the daily limits, open the three hand-checked demos,
go deeper on a finding, ask the report chat and share a read-only link.

| Checkpoint                                 | Revision                                          | Evidence                                                                            |
| ------------------------------------------ | ------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Stakeholder Brief release                  | 8c90443 (#67)                                     | Owner supplied Claude's backend-first rollout and production smoke results          |
| Most recent production accuracy evaluation | 613ab0c (#68), backend d9b5772, P3b off           | Claude's generic R1 handoff; merge exists locally                                   |
| New rule/verifier candidates               | Rules 091ee10; integration 1a75227; tools 0721c82 | Local commits and offline checks only; independent review and release checks remain |

This documentation pass did not query AWS, deployment logs or the live site. The
production rows are attributed release/evaluation checkpoints, not a new drift
or deployment certification. See [current status](current-status.md).

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
- **Order when both change:** apply the backend first, then merge. The
  merge deploys the frontend with no approval step after it, so the
  backend has to be ready before the merge. Old and new halves must work
  together for the gap between the two (as ADR-0062 §9 required).
- **Reading the plan** (learned on PR #67): in a fresh worktree, copy the
  ignored `terraform.tfvars`, `backend/build/trivy-layer.zip` and corpus
  chunks from the main checkout first. A missing Trivy zip shows as
  `source_hash -> null` and fails the apply partway. Functions whose code
  didn't change can still appear as updates when the live zips were built
  from a checkout with different line endings: download them
  (`aws lambda get-function`) and compare with `diff -rq
  --strip-trailing-cr` before applying. IAM policies that list function ARNs
  show as "known after apply" while those functions update; their content
  doesn't change. Anything else unexpected: stop.
- **After the apply:** a fresh plan must show no changes. Then run
  `node scripts/smoke_live.mjs https://archibrief.dev https://api.archibrief.dev`
  and check the changed functions' logs for errors before merging.

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
| Data residency rule | Hard test 3's EU residency breach (driver documents replicated to us-east-1) was missed by rules and model. A deterministic rule comparing resource Regions with the stated requirement is next. |
| Model blind spots | 30+ resource types with no settings or details (Redshift, EKS clusters, EventBridge policies, AMI permissions among them) and unevaluated modules ([coverage](terraform-coverage.md)). Four of hard test 3's eight criticals sit in them. |
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
