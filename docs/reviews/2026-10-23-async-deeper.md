# Asynchronous deeper review — P05 continuation

The previous HTTP path gave AgentCore 24 seconds. Deeper analysis now uses a
Standard Step Functions job outside the HTTP request. Report pricing, dollar
amounts, cost labels, effort estimates and aggregation are unchanged. Fernando
explicitly deferred that work; internal evaluation spending controls remain in scope.

## Contract and failure behavior

POST still requires the review's write capability and a parent in its original
ledger. It reserves the existing allowance once, conditionally stores a
`JOB#<parent>` row, and returns 202 with job ID, parent, status and absolute
deadline. Completed results retain the existing 200 response (or the existing
502 plus quality envelope when all proposed output was rejected). Missing-context,
expired-review and unauthorized requests do not dispatch a job.

The execution name and identifier-only input are stable for that review/parent.
An uncertain StartExecution response can be recovered using the same request,
not a new model attempt. This uses the existing initial-review pattern and
[Standard StartExecution idempotency](https://docs.aws.amazon.com/step-functions/latest/apireference/API_StartExecution.html).

A distinct worker Lambda claims pending -> running conditionally. Duplicate
delivery, workflow redrive, and repeated HTTP requests cannot invoke the model
again after that claim. The worker reads original evidence itself; no brief,
answers, findings, capability tokens or rejected text enter the workflow input.
Exceptions are reduced to fixed failure codes; logs record only exception class.

Timeout ordering is explicit: model read 300 seconds, worker 350, task 360,
workflow 400, saved job deadline at most 420. There is no paid-task Retry rule.
A Catch invokes status-only cleanup. Completion commits children, result marker
and job status atomically while the job is still running and unexpired. A late
result cannot overwrite cleanup, and cleanup cannot overwrite a committed result.
Review expiry remains unchanged. Failed/uncertain attempts are not automatically
rerun; a new paid-attempt UX is outside this contract.

GET report includes allowlisted `deeper_jobs` separately from output quality.
Job rows are not findings. The frontend polls only reads, resumes pending jobs
on reload, tolerates transient read failures, cancels obsolete requests, and
aborts even a stalled fetch at the absolute deadline. Saved findings remain
usable on failure. JSON and HTML retain job status; the original S3 ledger is
never rewritten. Legacy synchronous success responses remain supported.
An unreadable/stalled status response stops client polling without inventing a
server-side job failure: the UI preserves the last saved status and says it
could not confirm the result. Reload recovers the authoritative state.

## Deployment boundary

The API role can start only this state machine and cannot invoke AgentCore.
The worker reads only reports/, reads reviews, updates the findings table, checks
the kill switch, and invokes the configured runtime. KMS decryption is scoped
to the existing source key through S3. Workflow logs exclude execution data;
Lambda and workflow log groups have explicit retention. Both entrypoints ship
in the same pinned Lambda package, whose transitive imports are tested.

Before release, provision the worker/workflow and new client, drain any old
synchronous in-flight requests, then switch admission. No deployment, AWS provider
initialization/plan, live model call or paid evaluation was performed here.

## Validation

- Backend: 1,113 passed, 5 skipped, 26 documented coverage gaps deselected.
- Frontend: 82 unit tests; full 74-browser suite passed, then all 5 critical-path
  tests passed after adding the stalled-read scenario.
- Moto tests cover real conditional writes/transactions, one reservation and
  execution, uncertain dispatch recovery, duplicate delivery, paused/expired
  jobs, all-rejected replay, late completion, immutable base evidence and reload.
- Infrastructure tests decode the real ASL with the existing HCL resolver and
  verify timeout ordering, identifier-only payloads, no retries, logging and grants.
- Ruff, ESLint, TypeScript and formatting passed. Trivy infrastructure scan found
  no unaccepted HIGH/CRITICAL findings. Frozen answer-key hash is unchanged.

P05 asynchronous source implementation is complete; deployed behavior remains
unverified. P06 money/effort work is deferred by user instruction. P07–P09 evaluator
quality/accounting and internal spending admission, followed by typed coverage,
remain open.
