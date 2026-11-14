# EU dispatch exceptions platform
Production staff-only dispatch service for a European freight cooperative.
All operations, including overrides and internal dispatch exports, require staff
authentication. The dispatch image relies on infrastructure authorization and
does not authenticate callers itself. The JWT issuer is externally operated.
The maintenance instance only needs read-only diagnostics and belongs in a private
application subnet. The edge subnet may be public. Public management is forbidden.
PostgreSQL records and DynamoDB journal are authoritative, have no independent
backup/replay, and require a 15-minute RPO. The database needs cross-AZ availability
with a 15-minute target recovery time. Evidence objects and all retained versions
must stay in EU AWS Regions and be recoverable for at least 90 days; this is the
customer's contractual placement requirement, not an invitation to infer laws.
Failed standard-queue messages receive daily inspection. Debug output is high-volume,
non-audit data needed for 30 days; audit logs require 90 days. The scratch importer
was retired, and no external stack attaches its regenerable disk. SNS subscribers
are managed by the central platform. Review every entry path and provider alias.
This is a synthetic static-review fixture, not a deployment package. Account IDs,
AMI IDs, image digests and ARNs are fictional identifiers. Application artifacts
and the existing central-operations SNS receiver are outside this Terraform root;
their availability is not asserted. The central platform owns account audit trails,
alert delivery, and organizational controls, which are not supplied for verification.
Do not infer an actual deployment, traffic volume, compromise, or effective SCPs.
Review the submitted configuration and these requirements across all issue areas.
No customer-managed encryption key is required unless explicitly stated.
