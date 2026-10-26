# Independent review of `codex/report-contract-redesign` — 2026-10-24

Reviewer: Claude. Scope: all 15 commits `4fb3ac4..8daf0de` (138 files,
+9,929/−935), starting from [release readiness](../release-readiness.md) and
the dated ledgers in this folder. Read-only against AWS; no push, merge,
deploy, paid evaluation or worktree command. Frozen fixtures, historical
results, demo outputs, report prices, effort estimates and aggregation code
were not edited.

Check items off as they are resolved. Severity: **Blocker** (must fix before
deploy), **Decision** (needs Fernando's call), **Should** (fix before or with
merge), **Note** (record only).

## Prioritized findings

### Blockers

- [x] **B1 — Deploy role cannot create the deeper workflow's log group.**
  `infra/modules/api-gateway/deeper-jobs.tf` named it
  `/aws/vendedlogs/states/<prefix>-deeper-review`. The deploy role's log-group
  statement allows only `/aws/lambda/archibrief-dev-*` and
  `/aws/states/archibrief-dev-*` (policy 02, local proposed copy), so the apply
  would fail with AccessDenied partway through. The review workflow already
  uses `/aws/states/<prefix>-review`.
  **Corrected in this review** (uncommitted): renamed to
  `/aws/states/<prefix>-deeper-review`; `terraform fmt` passes.
- [ ] **B2 — The backend and frontend must ship together.** POST `/deeper` now
  returns **202 + job** instead of 200 + findings. The live frontend
  (`4fb3ac4` `requestDeeperFinding`) expects findings, so if the backend goes
  first, "Go deeper" shows "no new findings" while the job runs unseen. Deploy
  the frontend in the same window, and expect already-open tabs to misbehave
  until they reload.
- [x] **B3 — No fresh `terraform plan` yet.**
  **Done 2026-10-24 (read-only, nothing applied):** with the B1/D1/S1 fixes,
  **11 to add, 24 to change, 0 to destroy.** Adds are exactly the deeper-job
  stack (worker Lambda + log group, two roles, four role policies plus the
  logs attachment, state machine + log group). Changes are the IAM edits (Query
  on the findings table for get_review/chat, StartExecution for deeper_review),
  new env vars, and code hashes for 17 Lambdas (shared modules they import
  changed). Three items are artifacts of planning from this checkout, not real
  changes: `runtime_code` (source path only; the runtime zip came from the main
  checkout because `uv` is missing here), `trivy_layer` (layer zip not built in
  this checkout, so `source_hash` is null), and the review worker/state machine
  policies (deferred data-source reads). Re-plan from the deploy checkout after
  building all packages before applying.
  Original finding: The ledgers record HCL parse, fmt
  and Trivy, but not provider-schema validation or a plan. A plan is needed to
  confirm the new resources (worker Lambda, two IAM roles, state machine, log
  group) and the IAM edits on five existing roles.
- [ ] **B4 — Rebuild and redeploy everything together.** That means the Lambda
  zips (`deeper_review` now ships `worker.run_job` too; ingest, rule engine,
  finalize, review worker, get_review, ask/list questions) and the **AgentCore
  runtime** (graph state `model_output_counts`/`parent_finding`, prompt versions).
  Mixed versions degrade safely to "unknown" quality, but the deeper context
  improvements only exist once the runtime is redeployed.

- [ ] **B5 — The live AgentCore runtime is already behind master.** The
  deployed runtime is byte-identical to the 2026-10-20 build (the plan showed
  no content change against that zip). Master's 2026-10-22 merge turned off SDK
  retries for the runtime's embedding, guardrail and model clients
  (`runtime_entrypoint.py`), so the live agent can still retry, and pay for, a slow
  call. It was never rebuilt because `build_runtime_package.py` needs `uv`,
  which the venv lacked. **`uv` 0.13.5 is now installed** in the main checkout's
  venv. The script also failed on a fresh checkout (it wrote the temporary zip
  before creating `build/`). **Fixed** here; the package now builds (29.4 MB).
  Rebuild and deploy the runtime with this branch, or on its own first.

### Decisions for Fernando

- [x] **D1 — Budget aggregation changed despite "leave aggregation untouched".**
  `backend/shared/report.py::stakeholder_view` now passes only findings whose
  assessment action is not `unknown` into `build_stakeholder_view`. On master,
  findings without an explicit `concern` were priced via
  `infer_concern(finding.finding)`, a text match. Model findings without a
  structured `plain` severity/needs_action, and every finding in live reports
  created before deploy, therefore drop out of the guided budget totals. The
  ledger states this is deliberate (avoiding a title-derived price contradicting
  the canonical assessment). It is defensible, but it changes which findings
  are summed, which is the aggregation you asked to keep. Options:
  keep it (document it as a deliberate change), or revert to pricing every
  finding and leave unassessed ones labeled.
  **Resolved: reverted** to master behavior per the standing instruction;
  regression test `test_unassessed_findings_stay_in_the_budget`. Historical
  ledger `2026-10-23-report-redesign.md` still describes the earlier filter.
- [x] **D2 — A failed deeper job is permanent.** A job that ends `failed`
  (timeout, kill switch, invalid output) returns 409 `deeper_job_failed`
  forever for that finding, and its reservation is not refunded. The ledger
  documents this as intentional (no automatic paid retry). Decide whether
  visitors should get one manual retry later.
  **Resolved: kept as designed**; README now states it.
- [x] **D3 — Docs are written from the branch's point of view.** The README
  ("This candidate runs Go deeper as a background job…") and the case study
  ("The local redesign branch now…", "These changes still require review and
  deployment") read as unfinished work on the public repo once merged. Merge
  together with the deployment, then reword to present tense, or keep the
  wording and merge only after deploy.
  **Resolved: reworded** to present tense. Consequence: merge this branch
  in the same window as its deployment (see B2).

### Should fix

- [x] **S1 — Day-boundary edge case in deeper admission.** The handler
  reserves (`reserve_operation`) before writing the job row. If the Lambda dies
  between the two and the visitor retries after UTC midnight, the reservation
  raises `operation_expired`, so a 409 with no job. This is rare, but the finding
  then can't go deeper that day or later. Write the job first, or treat an
  expired same-digest claim as recoverable.
  **Fixed:** `operation_expired` now recovers without a second charge (the
  claim key pins this exact finding); test
  `test_paid_claim_from_an_earlier_day_recovers_without_a_second_charge`.
- [ ] **S2 — Jobs can stay "pending" if dispatch never succeeds.** When
  `StartExecution` keeps failing (503 `deeper_dispatch_unavailable`), the row
  stays `pending` until its deadline (≤420 s), and then `public_job` reports
  `failed/timed_out`. That's acceptable, but the frontend message for 503 tells
  the user to retry, which re-dispatches idempotently. Confirm this path in the
  live smoke test (L-list below).
- [x] **S3 — The polling effect restarts on every poll.** In
  `report-workspace.tsx`, the effect depends on `report.deeper_jobs`, and each
  successful poll calls `setReport`, so every poll tears down and recreates
  the effect. It works (2 s cadence, deadline enforced), but it is accidental
  control flow. Consider a ref for the active job set.
  **Fixed:** the effect is keyed on the active job IDs/deadlines and
  schedules its own next poll.
- [x] **S4 — The evaluation usage capture assumes sequential calls.** The `after-call`
  hook in `evaluation_budget.py` records usage from any call on the shared SDK
  client while registered. That's correct for today's sequential runners; it
  would misattribute usage if a runner ever goes concurrent. Add a comment or
  assertion.
  **Fixed:** documented at the hook registration.

### Notes (verified, no change needed)

- Deeper job idempotency holds: deterministic job ID/execution name,
  conditional `pending→running` claim, no SFN `Retry`, a `Catch` → status-only
  cleanup, and an atomic `TransactWriteItems` of children, `RESULT#` marker and
  `running→complete` (max 98 + 2 = 100 actions, the DynamoDB limit). A late
  result can't overwrite cleanup.
- Timeout ordering is consistent: AgentCore read 300 < Lambda 350 < task 360 <
  workflow 400 < job deadline 420. A workflow-level timeout isn't catchable,
  but the job then reads as `failed/timed_out` once past its deadline.
- Durable assembly: the S3 ledger is never rewritten; children are validated,
  scoped to the review, parent-checked and deduplicated; incomplete batches are
  dropped and counted; pagination follows `LastEvaluatedKey` with a hard page
  bound. Only deeper writes to the findings table, so base findings don't
  inflate `excluded_child_count`.
- Deploy-role coverage for the new names: Lambda, state machine, IAM roles
  (`archibrief-dev-*`) and `iam:PassRole` to `lambda`/`states` all match.
- IAM scope: the API role can only `states:StartExecution` on the deeper
  machine (it lost AgentCore invoke); the worker gets read-only S3 `reports/*`,
  findings-table Get/Put/Update, the kill-switch parameter, the AgentCore runtime
  and S3-scoped `kms:Decrypt`. Workflow log delivery `Resource "*"` is the
  AWS-required form.
- Terraform conclusions are conservative: SQS mapping (function timeout >
  queue visibility, both known integers) matches the documented Lambda
  constraint; single-AZ placement requires every instance AZ known and
  identical; the versioned-retention gap requires Enabled versioning, all-object
  current expiration and *every* enabled rule lacking noncurrent expiration.
  Unknown/dynamic input yields no finding.
- Provider parsing keeps only `region` (plus alias); credentials are never stored.
- Evaluation accounting: fail-closed wrapper (unlisted methods denied),
  admission journaled before dispatch, failed calls keep their reservation,
  `monetary_limit_enforced: false` is stated honestly.

## Deployment and migration checklist

- [x] Apply the B1 fix (done locally) and include it in the branch.
- [ ] Rebuild Lambda packages and the AgentCore runtime image.
- [ ] Fresh `terraform plan`; review the new IAM roles/policies and the five
      edited role policies.
- [ ] Check that no synchronous deeper request is in flight (old path), then
      apply and deploy the frontend in the same window.
- [ ] Live smoke test: go deeper on a real review (202 → complete), reload
      mid-job, kill switch during a job, a second click on the same finding
      (no second charge), and an old report from before deploy (children,
      budget, chat all load).
- [ ] Remove the D3 branch-perspective wording after deploy.

## Validation run in this review

| Check | Result |
|---|---|
| Backend `pytest tests/backend -m "not coverage_gap"` (Python 3.14.3, main checkout venv) | 1,234 passed, 5 skipped — matches the release handoff |
| Ruff check / format (backend) | Passed / 105 files formatted |
| Frontend unit (`npm test`) | 83 passed |
| `tsc --noEmit`, `eslint --max-warnings=0` | Passed |
| Tooling tests | 4 passed |
| Playwright full suite (2 workers) | 75 passed (1.9 min) |
| `terraform fmt -check -recursive infra` (after B1 fix) | Passed |

Not run: a provider plan, a real AWS deployment, paid model evaluation and
CI on Python 3.12. These remain gates in [release readiness](../release-readiness.md).
