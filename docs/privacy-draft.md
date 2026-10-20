# Privacy notice draft — do not publish as current deployed behavior

The seven-day access boundary, cleanup settings, Turnstile, HMAC visitor
identifiers and capability-bound uploads below are built but not yet deployed
or verified against AWS; anonymous access is off. See
[public access design](public-access-implementation.md) for release limits.

ArchiBrief processes the Terraform archive, workload description, clarification
answers and questions you submit to create an architecture review. AWS storage,
compute and Bedrock services process this information. Do not submit secrets,
personal/customer records or confidential production data. Automated checks can
miss sensitive information, and generated findings can be wrong.

The proposed public flow uses Cloudflare Turnstile and a keyed hash of the
API-observed network address to limit abuse. Hashes remain pseudonymous
identifiers. Read capabilities can be shared; writes also depend on the
original network grouping. The browser stores capabilities in tab session
storage, so closing the tab loses access. Actual provider policies, regions
and retention still need verification before publication.

The current service is gated for the site owner. Public saved demos are separate
examples. Anonymous review submission is not open. Before enabling it, this
notice must explain the deployed anti-abuse provider, network identifiers,
capabilities and sharing behavior, with links to provider privacy policies.

The prepared application code stops serving a review and accepting follow-up
work at its original seven-day deadline, or an earlier explicit expiry. It also
rejects records without a trustworthy lifetime. Copying answers and finishing a
review do not renew that deadline. This describes the proposed release's access
behavior, not a guarantee that stored copies disappear at that instant.

Cleanup is asynchronous. S3 object versions, DynamoDB TTL deletion, backups,
workflow execution history and operational logs have different lifetimes.
Historical Standard workflow history includes submitted/derived content and
has a separate retention period. New local source limits workflow state to
identifiers/status and stores content in S3; this is not yet deployed. Turning off CloudWatch payload logging does not
erase that history. Exact physical-deletion, backup and log periods must be
verified and disclosed before publication. No blanket seven-day deletion or
provider no-retention/no-training claim is established here.

Before publishing, add the operator identity, working privacy/deletion contact,
verified processing region, provider feature/data-use policies, retention
inventory, and the date the final notice takes effect. Reconcile the notice with
the deployed system and the acceptance evidence in `public-access-plan.md`.
