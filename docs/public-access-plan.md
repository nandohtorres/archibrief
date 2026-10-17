# Public access: implementation and release boundary

Status: implemented locally, disabled and not deployed. See
[public-access-implementation.md](public-access-implementation.md) for the
contract, commits, evidence, limitations and exact release checklist.

Source now includes server-issued review IDs, conditional checksum/version-bound
uploads, separate capabilities, recoverable grants, Turnstile verification,
shared transactional admission across paid paths, a Regional REST/WAF stage,
and identifier-only workflow state. The existing HTTP API stays admin-only.
Neither public activation flag is enabled. Cached results and follow-up work
still require a live review within its original lifetime.

Local tests are evidence of mocked behavior, not live IAM, WAF bypass prevention,
real DynamoDB concurrency or model quality. No Terraform command, AWS call or
paid evaluation verified or deployed these changes. Legacy content-bearing
workflow history, backups and asynchronous deletion remain privacy work.

Before launch: build and review artifacts; validate/plan configuration; deploy
admin-only; verify every endpoint/stage and real quota race; drain legacy
executions; inventory retained content; complete upload-secret checks; finalize
the privacy notice; and run the bounded paid evaluation. Follow the detailed
release order in the implementation report. Keep anonymous access disabled
until that evidence is reviewed.

The IAM boundary description cleanup is a real resource-metadata change; a
future plan must inspect replacement/attachment effects. No zero-change
infrastructure plan is claimed.
