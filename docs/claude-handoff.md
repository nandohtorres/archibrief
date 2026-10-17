# Claude handoff — ArchiBrief

Codex prepared the public-access safety layer locally. **Nothing was pushed or
deployed. Public submissions remain disabled.** This needs review before launch.

## Where the work is

- Worktree: `C:\Users\ferna\cursor projects\side-projects\archibrief-cleanup-codex`
- Branch: `mobile-laptop/chore/codex-public-cleanup`
- Latest implementation/report commit: `35500a1`; based on `9871be0`.
- Six commits: `2dd5370`, `9fa89f1`, `feab86c`, `04d118f`, `dec8c15`, `35500a1`.
- Review the complete change with `git diff 9871be0..35500a1`.

## What changed

Server-issued review IDs; checksum/size/version-bound conditional S3 uploads;
recoverable upload grants and dispatch retries; separate read/write capabilities;
shared atomic quota reservations across initial reviews, clarification, deeper
review and chat; server-verified Turnstile; a proposed Regional REST/WAF front
door while the existing HTTP API stays admin-only; identifier-only workflow
state with content stored in S3. Browser tokens are tab-scoped. Both public
activation flags remain false. Packaging manifests, tests and docs were updated.

## Verified locally

700 backend tests passed, 5 skipped; 58 frontend unit tests and 66 browser tests
passed. Application lint/type/format checks passed. Offline Trivy passed with
existing exceptions; production npm audit found zero issues. HCL parsing passed
for 56 files, **not Terraform validation**. Tests use mocked services; real
concurrency, IAM and WAF behavior are unverified. ZIP artifacts were not built.
Remaining findings: 19 development dependency advisories and 15 test-helper lint
issues. Shared spending reservations are estimates, not an AWS billing ceiling.

## Next

Review code/IAM and retry/failure behavior first. Then, only with explicit
authorization, build artifacts, validate/plan infrastructure and deploy
admin-only for real bypass, upload/version and quota-race checks. Historical
workflow content/backups, upload-secret checks, final privacy disclosure and
bounded paid model evaluation remain launch work. No seven-day physical-deletion
guarantee is established.

Standing restrictions: **no push, AWS calls, Terraform commands, paid model runs,
history rewriting or file deletion** unless explicitly authorized otherwise.
Coordinate worktrees with parallel sessions; do not assume this branch is merged.

Details: [implementation report](public-access-implementation.md),
[test evidence](evidence/public-admission-checks.json),
[paid-evaluation runbook](evaluation-runbook.md).
