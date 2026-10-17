---
created_by: Codex
contributors: [Fernando]
review_status: draft - design only, not approved for deployment
created: "2026-10-16"
updated: "2026-10-16"
---

# Gate 2: anonymous public access design

This is a proposal built on F09–F12 in `archibrief-checkpoint-review-Codex.md`
and the code at `8d391b0`. Nothing here was deployed, no AWS calls were made,
and no infrastructure or protected implementation files were changed. The
repository copy preserves the task in a local commit; the requested delivery
copy is in Leonardo's `AI-Drafts/Codex/` folder.

## Verified starting point

| Finding | Current code evidence | Required public boundary |
|---|---|---|
| F09: admission/cost | `infra/modules/api-gateway/main.tf`: `POST /reviews` directly invokes StartExecution; current routes use the admin authorizer. `backend/lambdas/deeper_review/handler.py` has an in-flight lock, not a shared daily reservation. | Admit every paid path through atomic accounting, with edge abuse controls. |
| F10: identity/upload binding | `backend/lambdas/create_upload/handler.py`: caller chooses review ID; key is `uploads/{review_id}/archive.tar`. | Server-issued review and reservation IDs, write capability distinct from read capability, immutable object-version binding. |
| F11: retention | `infra/modules/s3/main.tf`: versioned bucket without expiration lifecycle. Reviews TTL configuration exists, but creation/finalization does not consistently supply an expiry; Findings/Audit lack equivalent expiry enforcement. | Shared absolute expiry, logical denial on reads and writes, physical cleanup of every copy. |
| F12: content propagation | `infra/modules/step-functions-lambda/main.tf`: execution data logging enabled, log retention 90 days; parsed content and brief travel in workflow state. | Keep user content out of durable workflow history and operational logs. |

Chat is a newer partial implementation: `ask_question` reserves a question,
review slot and daily model allowance in a transaction. Its preliminary quota
read is not atomic admission for input Guardrails: `GuardrailsClient.assess`
can run before `_reserve`. Concurrent rejected questions can therefore incur
screening charges outside that reservation. This is a protected-path finding
to fix in later implementation, not a change made in this task. Suggested
first-click answers also cost money even when they do not consume a typed slot.

## Front door: recommend Regional REST API with regional WAF

[AWS's comparison](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-vs-rest.html)
lists WAF support for REST APIs and not HTTP APIs. Stage throttles and CORS
are not substitutes for an enforced edge boundary.

| Choice | Benefits | Required work / risk |
|---|---|---|
| Regional REST API + WAF | WAF attaches to the API stage, including direct API requests. Fewer origin-secret and forwarded-IP assumptions. | Migrate integrations, authorizer payloads, errors, CORS and custom-domain mappings; regression-test every route. Usage plans still do not provide a hard spending cap. |
| Keep HTTP API behind CloudFront + WAF | Preserves HTTP integrations; edge filtering and one public domain. | Must independently authenticate the CloudFront-to-API hop; all API origin endpoints otherwise bypass WAF. More operational secrets and trust boundaries. |

Recommendation is design judgment, not a claim that REST is already configured.
Keep the existing admin gate throughout migration. Associate WAF with every
public REST stage, disable unused endpoints/stages, and test the default
hostname as well as custom domains. No public Lambda URLs or direct runtime
invocation grants should bypass admission.

If retaining HTTP API: give CloudFront a dedicated origin custom domain; disable
the default execute-api endpoint, and require a random origin credential on
**every** route at an authorizer before integration. CloudFront must overwrite
the viewer's same-named header. Missing/wrong credentials fail closed; compare
in constant time; rotate with bounded overlap; never log or expose the value in
browser code. Disable caching on bearer/private API responses and mutations.
Protect the custom origin hostname too: hiding DNS or disabling execute-api
alone does not prevent bypass. No assumption of REST resource policies or S3
origin access control applying to an HTTP API.
[AWS default-endpoint documentation](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-disable-default-endpoint.html)
and [custom-origin header behavior](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/add-origin-custom-headers.html)
support these mechanisms; the composite design still needs negative tests.

Use only edge-authenticated client IP metadata. Ignore caller-supplied
forwarded-IP headers; verify chain length and trusted proxy behavior. Turn the
trusted IPv4 address / IPv6 /64 into an HMAC using a versioned secret. Retain
only the identifier with a bounded expiry. Monthly rotation must not reset
allowances mid-day: pin the key version for the UTC bucket, or check both
versions during overlap. NAT unfairness and VPN evasion remain accepted limits.

## Admission and quotas on every paid path

Introduce an admission service rather than forwarding arbitrary request JSON
to StartExecution. Validate schema and lengths, check the kill switch, validate
visitor challenge/grant, then transact before any paid AWS screening, retrieval,
model, or workflow dispatch. Free reads still have edge/request limits.

One `TransactWriteItems` should conditionally update the global day allowance,
visitor bucket and review allowance, create a uniquely keyed operation record,
and update reservation status where relevant. Put conditions on each item's
Update; do not ConditionCheck and Update the same item twice in one transaction.
That restriction and all-or-nothing behavior are documented in
[DynamoDB transactions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html).

| Path | Admission/accounting contract |
|---|---|
| Upload issuance | Bound request count, active reservations, accepted bytes and quarantine retention before issuing a capability. One visitor review/day is ADR-0046's policy; abandoned reservation handling must not mint endless replacements. |
| Initial review | Consume one reservation; reserve worst-case bounded pipeline work, including Guardrails, embedding, retrieval, reasoning, retries and resume. Stable operation/execution ID prevents duplicate starts. |
| Clarification | Single conditional resume for the paused workflow. Recheck expiry and kill switch. Use the original reserved continuation budget or atomically acquire an additional allowance before resuming. |
| Go deeper | Consume a review question slot and global budget; distinct idempotency key plus request digest; a concurrency lock alone is insufficient. |
| Typed question | Reserve input screening before Guardrails, then bounded retrieval/model/grounding work. Rejections retain actual screening cost while freeing any unused reservation. |
| Suggested question | First generation reserves global paid work; repeats return the stored result. Concurrent first clicks share one operation. Slot exemption is not a cost exemption (ADR-0050 supersedes pregeneration in ADR-0046). |
| Retries, repairs, scheduled/pregeneration jobs | Same shared global ledger; no alternate handler/runtime invocation path can spend without a reservation. |

Use integer cost units and count backstops. Reserve a conservative maximum
from versioned prices, bounded input/output tokens, model/guardrail/retrieval
calls and retry counts. Keep unknown outcomes reserved until reconciled. Settle
exactly once with a conditional state transition; never refund the full amount
after a paid rejection or ambiguous timeout. A crash between reservation and
dispatch needs a durable outbox/reconciler, with stable execution name and
identical input. Do not blindly retry a model call when completion is unknown.

Pin every operation and later settlement to its original UTC budget bucket;
crossing midnight or expiring a stale lease must not create a new allowance for
the same work. TTL cleanup is not lock ownership or idempotency. Keep tombstones
long enough to cover all retry/reconciliation windows.

Admin may bypass visitor fairness limits, **not** the kill switch or global
budget. Changing this accepted ADR-0046 bypass scope needs Fernando's decision.
The global ledger bounds the reserved paid workload, not every possible AWS
bill: WAF/API traffic, rejected uploads/storage versions and logging still need
separate admission/size/rate controls. Budgets alerts are delayed backstops.
Do not publish numeric daily spend promises before measured costs and explicit
caps are approved.

## Turnstile and capabilities

Require server-side Siteverify success with expected hostname and action at
upload admission, before allocating a review. Use a separate challenge/grant
for the first paid chat action. Bind any short-lived signed visitor grant to
reservation/review, purpose, expiry and nonce; possession of a review URL alone
must not imply permission to consume arbitrary paid work.

[Turnstile validation](https://developers.cloudflare.com/turnstile/get-started/server-side-validation/)
documents single-use tokens valid for 300 seconds. Use its idempotency key for
verification retries; persist successful admission so an identical application
retry can return its reservation without reusing the token as a fresh request.
Reject changed request digests under the same application idempotency key.
Fail closed on timeout/unavailability, with a retry/sample option. No raw token
or secret enters logs, workflow state, analytics or reports.

Issue a cryptographically random server UUIDv4 review ID and separate random
upload reservation/capability. Store the exact bucket/key, size bound, expiry,
owner/grant hash and state. A read-only shared report link must not grant upload,
overwrite, clarification or paid-write authority. Prefer putting the bearer
token in a URL fragment exchanged for an authorization header; set a strict
Referrer-Policy, no indexing/third-party analytics, and redact route IDs in logs.
This refines ADR-0046's URL-as-access-token design and needs review.

Upload goes to quarantine. At completion, the server reads the exact object
version, validates actual length and computes SHA-256; do not trust the supplied
hash, Content-Type, ETag, or newest version of a key. Atomically bind version,
hash, review ID and reservation on submission. Ingest and Scan must read that
version, reject missing versions and never fall back to latest. Cross-review
reuse and overwrites fail even for valid bucket-prefix keys.

Current presigned POSTs are reusable until expiry and can accumulate versions.
A claimed one-use token in DynamoDB cannot stop repeated S3 uploads using the
same signed form. If a strict byte/request budget is required, use a bounded
upload gateway that atomically claims the capability before streaming an exact
length to a unique object. Otherwise explicitly accept residual repeated-upload
cost, shorten expiry, bound issuance and clean all versions. Do not call direct
presigned upload a hard storage cap.

## Secret scanning and retention

Use a maintained offline secret detector (the repo already uses Gitleaks for
Git; configure an archive mode separately). Safely extract under existing
archive limits, then inspect every admitted file, brief, clarification and chat
input before propagation to paid services or durable workflow state. Disable
online verification; redact matches and reject with generic categories, never
matched values or snippets. Scan failures fail closed. Detection is incomplete;
the upload notice must still prohibit secrets/customer data.

| Surface | Proposed policy and implementation |
|---|---|
| S3 uploads, intermediate content, reports | Absolute seven-day access expiry from admission; all reads/paid actions enforce it. Lifecycle covers current objects, noncurrent versions, delete markers and incomplete uploads. A version sweeper handles exact expiry and records failures; corpus/artifact buckets remain separately scoped. |
| DynamoDB review, findings, audit, Q&A | Same numeric `expires_at`/TTL across child records, including finalization and failures. No new question extends review lifetime. Deny expired data before serving/caching it; sweep if physical deletion needs a tighter service target. |
| Standard Step Functions | Identifiers, bounded stage/status/error codes and opaque object references only, never brief, parsed HCL, findings or chat text. States must discard returned content, errors must not contain excerpts, and old executions remain a separate cleanup/privacy issue. |
| CloudWatch and edge/WAF logs | Disable execution payload logging; structured metadata only. Proposed short retention must be configured for every group, including API, Lambda, AgentCore and WAF. Drop tokens, headers, raw IPs, review bearer paths and content. |
| Backups, exports, DLQs, caches, local temp | Inventory copies, define deletion/restore handling, no accidental content export. A restore must reapply expiry before serving. Cleanup temporary processing data on all exit paths. |

[S3 lifecycle](https://docs.aws.amazon.com/AmazonS3/latest/userguide/intro-lifecycle-rules.html)
treats current expiration and noncurrent versions separately. Noncurrent age is
not the same as upload age; lifecycle alone cannot prove exact deletion by an
absolute seven-day deadline. [DynamoDB TTL](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TTL.html)
deletes asynchronously, usually within days. Thus logical expiry and eventual
physical deletion must be described separately.

[Standard workflow history](https://docs.aws.amazon.com/step-functions/latest/dg/service-quotas.html)
normally remains 90 days after closure; AWS documents a support-request option
for 30 days, still longer than seven. CloudWatch retention changes do not change
that history. Existing payload-bearing executions cannot be declared erased by
this redesign. Keep public launch blocked until content is excluded from new
history and any historical exposure is understood.

## Privacy page draft — conditional on implementation and verification

> ArchiBrief reviews the Terraform and workload description you submit. Do not
> upload credentials, personal/customer records or confidential production data.
> Automated checks may miss sensitive information.
>
> We process submissions using AWS storage, compute and Bedrock models, and
> Cloudflare Turnstile helps protect the service from bots. These providers
> process technical request information. We keep a short-lived keyed identifier
> derived from your network address to apply fair-use limits; it is not an
> anonymous identity guarantee. We do not require an account or email address.
>
> Your report is accessible to anyone holding its read capability. Share it only
> with people you trust. Paid follow-up actions require additional admission.
> Reports can be wrong; this is not compliance certification.
>
> After seven days from admission, we stop serving your upload, report and
> conversation. Storage cleanup is asynchronous; older object versions and
> database records may remain until cleanup completes. Operational records have
> separate retention. Workflow identifiers/status metadata can remain for up to
> 90 days after a run closes; we exclude submission content from new workflow
> history. [Before publication, insert verified physical-cleanup targets,
> operational-log and backup periods, deployment region/provider policies,
> operator identity and a working privacy/deletion contact.]
>
> We do not use your submissions to train our own models. [Before publication,
> verify the selected provider features' data-use policies and link them; this
> draft does not establish a blanket provider no-retention/no-training promise.]

Do not publish this proposed copy as a description of today's system. F11/F12
are unresolved in the inspected checkout. No guaranteed seven-day physical
deletion or broad legal-compliance claim is supported.

## Acceptance evidence required before removing admin auth

- Direct origin/default/custom-stage calls cannot bypass WAF/admission; spoofed
  origin and forwarded-IP headers fail. Private responses never cross caches.
- Parallel last-slot attempts admit at most the allowance, across reviews,
  uploads, Guardrails-only failures, suggestions, deeper actions and resumes.
  Kill switch, dependency errors, cold starts, UTC rollover and replay fail safe.
- Crash injection around reserve/dispatch/settle proves no unreserved spending,
  duplicate dispatch/refund or leaked indefinite reservation. Measured maxima
  fit the configured conservative reservations.
- Cross-review upload/version/hash substitution, reused form/capability,
  oversized bodies, expired grants and replayed Turnstile challenges are covered.
- Seeded synthetic secret markers never appear in workflow history, logs,
  reports or model requests; test all rejection/error paths without real secrets.
- Expired data is inaccessible even while TTL/lifecycle deletion lags; deletion
  accounts for all versions, child rows, caches, backups and abandoned uploads.
- Privacy wording, measured costs and any changed ADR policy are reviewed;
  live verification/deployment remains a separate authorized task.
