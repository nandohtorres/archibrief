# Local hardening results — 2026-10-17

This continues `160f5fa` in the isolated `archibrief-cleanup-codex` worktree.
No push, AWS call, paid model call, Terraform command, history rewrite or file
deletion was performed as a project action. Tests used mocked AWS services.
Infrastructure edits below are proposed source configuration, not deployed
controls. Anonymous launch remains blocked; this is not completion of Gate 2.

## Commits and behavior

| Commit | Result |
|---|---|
| `7d4a922` | Reject non-object upload JSON; reject expired cached answers and suggestions; preserve copied-answer deadlines. |
| `daaa379` | Reserve screening cost/request count atomically before Guardrails, retain possibly billed failures, recover abandoned claims, and reserve remaining model work separately. |
| `28ab89e` | Decline model calls without enough remaining time; retain failed grounding estimates; align handler defaults with the deployment contract. |
| `b483f04` | Upgrade Vitest/Vite and lint dependencies; patch compatible transitive dependencies; select Node 24 in CI; add Python CI lock and typecheck gate; fix formatting/line endings. |
| `7daf29c` | Enforce original review expiry on reads, replay and follow-up work; cap chat TTL; bundle the shared expiry helper. |
| `34b5b03` | Guard paid reasoning evaluation, add offline previews/partial limits to both runners, and include chat input-screening estimates. |
| `409593f` | Persist review/audit/finding expiry, prepare prefix-scoped S3 version cleanup and DynamoDB TTL, disable CloudWatch workflow payload logging. |
| `0c14820` | Pin tested CI tools and test that all review/upload routes remain admin-gated. |
| `2a763b6` | Remove the remaining private-log reference from IAM resource metadata; future plan must inspect replacement/attachment effects. |

The source-file inventory can be reproduced with
`git diff --name-only 160f5fa..HEAD`. Changes cover backend handlers/shared chat
code and regression tests; packaging; CI/locks/line endings; the frontend chat
error message and a formatting-only landing-component change; four infrastructure
modules; and these evidence/design documents. Existing browser specs have no
functional changes. Dependency lockfile removals are package graph changes, not
deleted project files. No deployed resources were removed.

## Validation

Compact source evidence: [hardening-checks.json](evidence/hardening-checks.json).
Full local XML/JSON/logs remain in ignored `backend/build/`.

| Check | Result |
|---|---|
| Complete backend suite | 669 passed, 5 skipped; no failures/errors |
| Frontend unit | 56 passed in 10 files |
| Playwright | 60 passed; no skips, unexpected failures or flakes |
| Ruff, ESLint, TypeScript, default Prettier check | Passed |
| Staged secret scan | Passed each commit |
| Offline infrastructure Trivy gate | Passed with existing accepted exceptions |
| npm audit, all dependencies | 19 findings: 4 moderate, 15 high, 0 critical; previously 30 including 2 critical |
| npm audit, production only | 0 findings |
| Linux/Python 3.12 dependency resolution | Passed; Ruff/pytest/moto pinned to tested tool versions |
| Terraform plan/apply, live smoke, paid quality evaluation | Not run |

Four backend skips need the gitignored corpus and one real-Trivy unit test is
Linux-specific. Deterministic scanner traps still ran. The local environment is
Node 24.14.0 and the existing Python 3.14 venv; the Linux/Python 3.12 lock resolved
but was not executed locally or in remote CI. No new Python venv was created.

The first npm upgrade attempt hit a peer-resolution conflict; explicitly
upgrading the required Vite peer resolved it without `--force` or ignoring
peers. Sandbox runs hit network, pytest-temp-directory and tool-execution
restrictions; approved reruns resolved those environment failures. One quota
test exposed a zero-count configuration edge, fixed before commit. Expiry
fixture and canary errors were corrected before the passing final run.

The remaining npm findings include upstream issues without compatible patches
in the current Lighthouse/lint dependency trees. Compatible patches were applied
for compression and temporary-file handling. The full audit is not clean; do
not apply npm's proposed major downgrades blindly. Python CVE auditing was not
performed. Production-only npm results do not clear development tools or Python.

## What is still unfinished

The paid model-quality measurement remains pending, with an
[offline runbook](evaluation-runbook.md). No model pass rate was invented.

[Public admission](public-access-plan.md) still needs the WAF/front-door migration,
Turnstile, server-issued IDs/capabilities, immutable upload binding, and shared
visitor/global quotas for initial review, continuation and deeper review. The
new route tests guard the existing admin boundary; they do not implement those
controls. Keeping the service gated remains appropriate.

Retention changes are not a complete deletion policy. Historical rows need
review/backfill, backups have separate retention, and Standard workflow state
still contains content. The new S3 rules clean up versions asynchronously.
Disabling CloudWatch payload logging does not change execution history. The
[privacy draft](privacy-draft.md) must not be published as today's deployed
behavior. Infrastructure changes intentionally require a nonzero reviewed plan;
the former zero-resource-change cleanup claim no longer applies to this branch.

The unused guest-session table/GSI and broader handler/client refactors remain
future maintenance candidates. No resources/files were deleted to pursue them.
