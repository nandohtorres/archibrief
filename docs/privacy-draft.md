# Privacy notice draft (superseded)

This was the pre-launch draft, written while public submissions were still
off. It is superseded by the published notice, effective 23 October 2026:
[archibrief.dev/privacy.html](https://archibrief.dev/privacy.html), source
[`frontend/app/privacy/page.tsx`](../frontend/app/privacy/page.tsx).

The published notice covers what the draft left open: the operator, the
processing region (AWS us-east-1, including Bedrock), Cloudflare Turnstile and
the keyed network hash, how review keys are kept in the browser and shared
(ADR-0053), and retention by store. Retention is asynchronous: archives,
parsed input and reports are scheduled for deletion after seven days, review
records expire after seven days, DynamoDB recovery backups keep a copy for up
to 35 days, and logs and workflow history are kept 7 to 90 days depending on
the service. There is no seven-day physical-deletion guarantee.

When the system changes what it collects or keeps, update the published page
and the infrastructure it describes together (S3 lifecycle in
`infra/modules/s3/retention.tf`, DynamoDB TTL and point-in-time recovery in
`infra/modules/dynamodb`, log retention). The draft's earlier text is in git
history.
