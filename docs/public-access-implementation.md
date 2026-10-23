# Public access design

**Status: built and tested, switched off.** The live site is admin-only. Two
flags (`public_access_enabled`, `chat_public_enabled`) stay false until the
release checks at the end of this document pass. Tests here prove mocked
behavior, not live IAM, WAF bypass prevention, real DynamoDB concurrency or
model quality.

## Uploads

`backend/shared/uploads.py` issues the review ID and a conditional S3 PUT. The
signature binds the exact byte length, SHA-256 checksum and
`If-None-Match: *`; the API accepts up to 20 MiB, and the upload lease lasts
900 seconds. Submission verifies the exact S3 version, digest and size before
binding the immutable input and starting a Standard execution with a stable
name. A retry with a changed body is a conflict.

A client nonce recovers the same grant after a lost response, without another
upload reservation or a renewed expiry. A server-side secret derives
unpredictable review capabilities, and the database stores only their hashes.
The browser keeps capabilities in tab session storage, never in URLs. Read
access is a transferable capability; writes also require the original visitor
identifier. Closing the tab loses browser access, and a network change can
prevent writes.

The upload role can list the reports bucket so a HEAD on a missing object
returns 404 rather than an ambiguous 403
([HeadObject](https://docs.aws.amazon.com/AmazonS3/latest/API/API_HeadObject.html)).
That permission is not part of the browser upload signature.

## Abuse protection

Cloudflare Turnstile is verified server-side for success, hostname (apex or
`www`) and the `archibrief-upload` action, with a bounded timeout, and fails
closed. The
secret lives in SSM, not in the repo. Visitor identifiers are an HMAC of the
address API Gateway observed (IPv6 grouped by /64); forwarded headers are
ignored. Admin calls skip the challenge.

Upload grants and the global and visitor upload counters share one DynamoDB
transaction. The launch limits are 6 uploads a UTC day globally and 2 per
visitor, close to what the paid budget can review. Abandoned reservations still count. The visitor HMAC
and reservation keys must stay stable while grants are active; rotating them
needs a migration.

## Spending limits

Every public paid path (initial review, clarification, deeper review, chat)
reserves estimated cost against global daily, visitor daily and review
lifetime allowances in the same transaction as its operation claim. Admin
requests reserve only a separate admin daily allowance, so public traffic
can't block the owner and owner reviews don't spend the public allowance.

The module defaults are in `paid_limits` (`infra/modules/api-gateway/admission.tf`);
the live values are set in `infra/environments/dev/main.tf`: global $1.20 and
15 requests a day (about three initial reviews), visitor $1.00 and 8, review
$1.00 and 10, admin $5.00. Initial reviews reserve $0.40; clarification and
deeper review reserve $0.20. A
`tests/backend/test_defaults_match_terraform.py` check fails if the handler
fallbacks drift from these defaults.

A review that fails before any billed call (paused, input rejected before
Guardrails, clarification limit) gives its reservation back once; the claim
stays, so the operation can't be dispatched again. Other failures and
successes keep the conservative estimate. Chat additionally settles its own
estimates in a chat-specific ledger. These are estimates, not an AWS billing
ceiling.

Duplicate requests reuse durable claims only where dispatch is idempotent, or
return the saved result. A claim from an earlier UTC day can't authorize new
paid work. Zero or invalid allowances fail closed.

## Front door

A Regional REST API `public` stage sits behind WAF: a 16 KiB body limit, a
300-request per-IP rate rule (answered with 429) and the AWS managed common
rule set, with sampled request bodies disabled. Stage-scoped Lambda
permissions stop other stages from using that grant. The stage has no
authorizer: each handler checks the public flag, capabilities, expiry and
CORS itself, so a header-based authorizer can't turn visitors away before
that check. API Gateway's own error responses carry CORS headers so the
browser can read them. The original HTTP API requires the admin key until it
is retired.

## Review pipeline and content

Step Functions inputs and results carry identifiers and status only, so
briefs, answers and findings never enter execution history. A worker Lambda
reads the submission, context and clarification objects under `jobs/` in S3
and runs the content-bearing stages. Stages that don't call the model retry
transient Lambda errors; the AgentCore call runs once, because a timed-out
model call may already be billed. The Step Functions task timeout (910 s)
sits above the worker's 900 s Lambda timeout, so the Lambda's own timeout
fires first. Executions started under the earlier payload-bearing state
machine must drain before migration.

Access ends at the review's seven-day expiry. S3 lifecycle rules cover
`jobs/`, uploads, parsed input, reports and noncurrent versions; DynamoDB TTL
and log retention clean up asynchronously, so there is no exact physical
deletion deadline.

## Validation

Compact evidence: [public-admission-checks.json](evidence/public-admission-checks.json).
The backend, frontend unit and Playwright suites cover the upload contract,
admission races (sequentially; Moto is not thread-safe), capability checks,
lost-response recovery and the browser upload flow. The backend changes are
applied to the live account with every public flag off; a follow-up
`terraform plan` shows no changes. The REST front door is not deployed yet.

## Before turning it on

1. Plan and apply are done, with every public flag off. Still to check
   against real services: the worker's failure path.
2. Deploy the REST front door with anonymous access off. Check the WAF
   association, that anonymous requests reach the handlers and are refused,
   CORS on handler and gateway errors, checksum/version HEAD, the conditional
   PUT, and default-endpoint and other-stage bypasses against real services.
   Only then copy the API ID into `verified_public_api_id`.
3. Open it at the REST URL without announcing it, with tight limits. Test
   real concurrent last-slot requests on every paid path, ambiguous dispatch
   failures, network changes and Turnstile outages, on both hostnames.
4. Measure per-review cost on a few real reviews and set the limits from it.
5. Inventory retained content and backups, and finalize the privacy notice.
   Don't promise seven-day physical deletion.
6. Cut over: point the frontend and `api.archibrief.dev` at the REST stage,
   and remove the admin key, the admin allowance and the HTTP API.
