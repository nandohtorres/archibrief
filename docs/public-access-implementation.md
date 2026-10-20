# Public access implementation ? 2026-10-17

Implemented and tested locally in `archibrief-cleanup-codex`, based on `9871be0`.
Public access remains disabled. Nothing was pushed or deployed; no AWS call,
Terraform command, paid evaluation, history rewrite or project-file deletion
was performed. This report supplements the earlier `hardening-results.md`.

## Changes and local commits

| Commit | Behavior |
|---|---|
| `2dd5370` | Server-issued upload reservations; separate review capabilities; shared atomic admission on review, clarification, deeper review and chat; identifier-only worker; packaging and regressions. |
| `9fa89f1` | Recover the same upload grant/version after a lost response; preserve the original deadline and quota; tighten dispatch retry conditions. |
| `feab86c` | Prepare a Regional REST API with stage WAF; keep HTTP admin-only; wire admission IAM, S3 versions/KMS, worker and identifier-only state machine. Flags stay false. |
| `dec8c15` | Permit bucket existence checks so recovery can distinguish a missing upload from denied access. |
| `04d118f` | Browser Turnstile, tab-scoped capabilities, checksum/version-bound upload, submission retries and six new browser tests. |

Exact files: `git diff --name-only 9871be0..HEAD`. Backend changes cover shared
admission/access/HTTP/upload helpers, API and pipeline handlers, agent retry
configuration and packaging. Frontend changes cover the submission flow,
API/contracts, capability storage, a maintained Turnstile dependency and test
builds. Infrastructure changes span API Gateway, orchestration, IAM, S3 and
hosting CSP. Existing browser spec files were not changed.

## Admission contract

`backend/shared/uploads.py` issues the review ID and conditional S3 PUT. It
signs the exact byte length, SHA-256 checksum and `If-None-Match: *`; the API
accepts up to 20 MiB. The upload lease lasts 900 seconds. Submission verifies
the exact S3 version, digest and size before binding the immutable input and
starting a stable Standard execution name. Changed-body retries conflict.

A client nonce recovers the same grant after response loss without another
upload reservation or a renewed expiry. An upload-only server secret derives
unpredictable review capabilities; the database stores their hashes. The
browser keeps capabilities in tab session storage, outside URLs. Read access
is a transferable capability; writes also require the original visitor HMAC.
The upload role can list the reports bucket so a missing-object HEAD returns
404 rather than an ambiguous 403, as specified by the
[AWS HeadObject contract](https://docs.aws.amazon.com/AmazonS3/latest/API/API_HeadObject.html).
That permission is not included in the browser upload signature.
Closing the tab loses browser access. IP/network changes can prevent writes.

Turnstile is verified server-side for success, hostname and action
`archibrief-upload`, with bounded timeout and fail-closed errors. The secret
is referenced from SSM, not committed. Trusted API request-context addresses
produce HMAC visitor identifiers; arbitrary forwarded headers are ignored.
IPv6 addresses use a /64 grouping. Admin calls bypass the challenge.

Upload grants and global/visitor upload counters share one DynamoDB
transaction. Defaults allow 100 uploads globally per UTC day, one per visitor
(100 for admin). Abandoned reservations consume allowance. Visitor HMAC and
reservation keys must stay stable during active grants; rotation can strand
access or reset visitor buckets and needs an explicit migration.

Every public paid path reserves global daily, visitor daily and review
lifetime allowance in the same transaction as its operation claim. Admin
requests reserve only a separate admin daily allowance, so public traffic
can't block the owner and owner reviews don't spend the public allowance.
Terraform sets every value explicitly (`paid_limits` in
`infra/modules/api-gateway/admission.tf`): public scopes 1,000,000 micro-USD
each with request limits of 100/30/20, admin 20,000,000 with no request cap.
Initial reviews reserve 400,000; clarification and deeper review reserve
200,000 micro-USD. Chat retains its staged screening/model reservations and
also participates in the same scopes. Suggestions use the same admission.
A review that fails before any paid call (paused, invalid input before Guardrails,
clarification limit) gives its reservation back once; the claim stays so the
operation can't be dispatched again. Other failures and successes keep the
conservative estimate; the chat-specific ledger separately settles its
estimates. These are estimates,
not an AWS bill ceiling, and do not cover every storage/network/service cost.

Duplicate requests reuse durable claims only where dispatch is intrinsically
idempotent, or return the saved result/in-progress. Old UTC-day claims do not
authorize fresh paid dispatch. Zero or invalid configured allowances fail
closed. Tests cover stale preliminary reads and conditional rejection; Moto
is not thread-safe, so they do not prove real-service parallel behavior.

## Front door and content

The proposed Regional REST `public` stage has a WAF association, a 16 KiB body
bound, a 300-request per-IP rate rule and AWS managed common rules. Sampled
request bodies are disabled. Stage-scoped Lambda invoke permissions prevent
alternate stages from using that grant. The old HTTP API always requires
admin authorization. API handlers enforce capabilities, expiry and CORS.
The default REST endpoint is behind its stage WAF; it is not an unprotected
CloudFront origin. Custom-domain migration is not included.

New state machine inputs/results contain identifiers and status only. The
worker reads submission/context/clarification objects under `jobs/` in S3,
invokes content-bearing stages privately and returns bounded status. Resume
callbacks carry an object key. No automatic retry repeats paid worker work.
Existing payload-bearing executions must drain with the legacy callback
shape before migration; their historical payloads are not erased. Pipeline
operational errors fail conservatively and may need a new review.

Logical access ends at the original seven-day review expiry. S3 lifecycle
rules include `jobs/` alongside uploads/parsed/reports and noncurrent versions;
DynamoDB TTL and CloudWatch settings remain asynchronous cleanup controls.
They establish no exact physical-deletion deadline. Backups, Standard history,
logs, exports, caches and historical records still require an inventory.

## Validation and failures

Reproducible compact evidence: [public-admission-checks.json](evidence/public-admission-checks.json).
Detailed test reports remain in ignored `backend/build/`.

| Check | Result |
|---|---|
| Complete backend | 700 passed, 5 skipped, no failures/errors |
| Frontend unit | 58 passed in 11 files |
| Playwright, fixture/admin/public builds | 66 passed, no skips, failures or flakes |
| Ruff on backend/scripts; ESLint; TypeScript; default Prettier | Passed |
| HCL syntax parsing | 56 files parsed; not Terraform validation |
| Offline Trivy HIGH/CRITICAL | Passed with existing exceptions, default and edge-enabled scanner inputs |
| Production npm audit | Zero findings |
| Staged Gitleaks | Passed on each local commit |

Four backend skips need the ignored corpus; one scanner test is Linux-only.
Trivy warned about unset deployment variables, so scanner evaluation is
partial. Native Windows Python 3.14/Node 24 tests do not replace Linux Python
3.12 execution, artifact packaging or provider validation. Packaging manifests
and their unit checks changed; deployable ZIP builds were not run here.

Failures corrected before the final run: the packaging SDK expectation, test
package discovery, an invalid threaded Moto test, DynamoDB Decimal sizing in
finalization, two incorrect browser button labels, and lost-response upload
recovery. The secret hook rejected two fake fixture literals; generated test
placeholders passed without scanner exceptions. Sandbox restrictions required
approved reruns for temporary directories, browser builds, scanners and audit.
The earlier full dependency audit still lists 19 development-tool findings
(4 moderate, 15 high); the production-only audit above is clean.
A broader Ruff run including all backend tests found 15 existing helper-style
issues; the configured backend/scripts check passes. They remain follow-up.

## Release work still required

1. Review a Terraform format/validate/plan and IAM changes after the standing
   no-Terraform/no-AWS restrictions are explicitly lifted. Review ZIP builds,
   KMS/SSM permissions, budget estimates and the worker's latency/failure path.
2. Deploy the REST edge with anonymous access off. Inspect WAF association,
   absent admin-header handling, CORS, checksum/version HEAD, conditional PUT,
   custom/default endpoints and alternate-stage bypasses using real services.
   Copy its verified API ID into `verified_public_api_id` only after checks.
   Public activation requires that ID and configured challenge secrets.
3. Test true concurrent last-slot requests across every paid path, ambiguous
   dispatch/callback failures, network changes, challenge outages and immutable
   object/version binding. Keep flags off until this evidence is reviewed.
4. Inventory historical content and backups, plan expiry backfill without
   extending lifetimes, complete upload-secret checks and finalize the privacy
   notice. Do not publish a seven-day physical-deletion promise.
5. Run the separately authorized bounded paid pilot in
   [evaluation-runbook.md](evaluation-runbook.md), with account/region and
   spending allowance agreed first. Then review deployment and launch evidence.
