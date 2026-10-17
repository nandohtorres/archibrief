# Public access: implementation and release boundary

Status: blocked for anonymous launch. This plan follows the cost, identity,
retention and content-propagation findings in `publication-review.md`. It is
not evidence that the proposed controls have been deployed.

## Completed locally

Chat reserves screening cost and a daily request atomically before Guardrails.
Rejected or failed screening retains that reservation; allowed screening then
reserves the remaining model allowance. Suggestions reserve their paid work
without consuming a typed-question slot. Cached responses must be live.

Review reads, chat, clarification and deeper review now reject expired or unknown
lifetimes. Legacy workflow records derive a deadline from their original
`createdAt`; an explicit TTL cannot extend it. New chat and deeper findings
inherit that deadline. Finalization persists review TTL, and audit records use
the original workflow start time. Historical records are not backfilled here.

Prepared infrastructure changes enable Findings/Audit TTL, clean up current and
noncurrent S3 versions in `uploads/`, `parsed/`, and `reports/`, and disable
CloudWatch workflow payload logging. No Terraform command or AWS call verified
or applied these changes. Lifecycle age is not an absolute deletion deadline.

`tests/backend/test_public_gate_contract.py` checks that every review/upload
route retains its admin authorizer and that public chat defaults to disabled.
The free saved demo remains available.

## Remaining implementation, in dependency order

1. **Front door:** prefer Regional REST API with WAF attached to the stage.
   [AWS documents WAF support for REST, not HTTP APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-vs-rest.html).
   The alternative is the existing HTTP API behind CloudFront/WAF, with a
   dedicated origin domain, default endpoint disabled, and a rotating origin
   credential checked on every route. Hiding an origin hostname is insufficient.
   Test direct default, custom-domain and alternate-stage bypasses. Retain admin
   authorization during migration. This choice is proposed, not implemented.
2. **Visitor admission:** validate Turnstile on the server, including expected
   hostname/action, then issue a short-lived grant bound to the operation.
   Tokens are single-use and expire after five minutes; a browser widget alone
   is insufficient. See [Cloudflare validation](https://developers.cloudflare.com/turnstile/get-started/server-side-validation/).
   Fail closed on validation errors. Use edge-authenticated client addresses,
   bounded HMAC identifiers and UTC buckets; never trust arbitrary forwarded IPs.
3. **Upload reservation:** issue the review ID on the server. Separate read and
   write capabilities; persist only capability hashes. Bind owner/grant, exact
   object key, size, digest, S3 version and absolute expiry. Verify the version
   before dispatch. The current client-selected ID and reusable presigned POST
   do not provide this contract. Bound abandoned reservations and upload bytes.
4. **Shared paid admission:** replace direct `POST /reviews` → StartExecution
   with admission before dispatch. One transaction must reserve global cost,
   visitor allowance, review allowance and a digest-bound operation claim.
   Initial review, clarification/resume, deeper review, first suggested answer,
   typed chat, Guardrails, retrieval and retries all need explicit accounting.
   Existing chat accounting does not close the initial/deeper/visitor gaps.
   Distinguish count limits from dollar estimates and total AWS billing.
5. **Dispatch and recovery:** use a stable execution ID and durable operation
   status. Handle transaction conflicts, start-call timeouts and ambiguous paid
   failures conservatively. Never refund potentially billed work blindly.
   Expired capabilities and requests must not resume workflows or extend TTL.
6. **Content isolation:** change workflow state to identifiers/object references
   rather than briefs/findings. Disable payload logging throughout the path,
   audit errors for excerpts, and sanitize metadata. Disabling CloudWatch
   payload logging alone leaves Standard execution history unchanged.
7. **Deletion inventory:** backfill trustworthy absolute expiries without
   renewing old content. Inventory S3 versions, DynamoDB records/PITR, workflow
   history, logs, exports, caches, DLQs and local temporary data. Do not execute
   deletion or backfills as part of this source preparation.

## Release evidence

Require parallel last-slot tests across every paid path; duplicate grants,
changed-body retries, object replacement/version mismatch, expired reads and
resumes, challenge outages, spoofed proxy metadata, dispatch timeouts and
recovery. Inspect actual AWS permissions and front-door behavior after an
authorized deployment. Run the paid quality evaluation separately.

Standard [execution history retention](https://docs.aws.amazon.com/step-functions/latest/dg/service-quotas.html)
is separate from CloudWatch and exceeds seven days. Historical payload-bearing
executions and backups remain part of the privacy inventory. Keep anonymous
access disabled until these implementation and verification items are complete.

The IAM boundary description cleanup is a real resource-metadata change and
must be reviewed in a future plan for replacement/attachment effects. This
branch intentionally no longer claims a zero-change infrastructure plan.
