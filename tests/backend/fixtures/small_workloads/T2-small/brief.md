# Equipment inspection records
Production records platform used by dispatch staff. records is the authoritative
PostgreSQL database; journal is the authoritative DynamoDB event history. Neither
has an external backup or independent replay source. Both require recovery from
accidental writes/deletes with a 15-minute RPO. The database must survive one AZ
failure with a target recovery time of 15 minutes. A cross-AZ subnet group alone
does not establish a standby. The database must not be internet accessible.
Evidence documents are uploaded to stable keys that can be overwritten; originals
and superseded versions must remain recoverable for at least 90 days. There is
no separate archive. Failed standard-queue messages are inspected every day.
High-volume debug logs contain no audit evidence and are needed for only 30 days;
audit logs are needed for 90 days. The scratch importer was retired, its disk is
regenerable, and no external stack attaches that volume. Do not invent dollar costs.
Sessions set expires_at on every item; application checks enforce session expiry
immediately, while physical deletion may take days. AWS-managed encryption is fine.
Full-size scope adds five recomputable reporting archives (monthly rollups, vendor
statements, capacity forecasts, route scorecards, inventory digests); each needs
90-day current/noncurrent retention. The small deployment has no reporting archives.
This is a synthetic static-review fixture, not a deployment package. Account IDs,
AMI IDs, image digests and ARNs are fictional identifiers. Application artifacts
and the existing central-operations SNS receiver are outside this Terraform root;
their availability is not asserted. The central platform owns account audit trails,
alert delivery, and organizational controls, which are not supplied for verification.
Do not infer an actual deployment, traffic volume, compromise, or effective SCPs.
Review the submitted configuration and these requirements across all issue areas.
No customer-managed encryption key is required unless explicitly stated.
