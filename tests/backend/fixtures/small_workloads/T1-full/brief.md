# Contractor access and export service
Production maintenance service for a regional equipment-rental business. The
maintenance worker only needs read-only operational diagnostics and must remain
in a private application subnet. Contractors authenticate before any export.
The contractor_export Lambda produces internal shift/contact extracts; its image
does not implement authentication and relies on infrastructure access controls.
The private spare group is reserved for a future internal host; no host uses it.
No approved requirement permits public SSH or administrator permissions here.
The edge subnet is reserved for future public ingress and may route to the IGW.
Full-size scope adds five separately owned, recomputable export archives for
vendor catalogs, shift rosters, dispatch summaries, inspection indexes and stock
snapshots. Each requires 90-day current/noncurrent retention and private TLS access;
the small deployment has no such archives. These do not change the core service.
This is a synthetic static-review fixture, not a deployment package. Account IDs,
AMI IDs, image digests and ARNs are fictional identifiers. Application artifacts
and the existing central-operations SNS receiver are outside this Terraform root;
their availability is not asserted. The central platform owns account audit trails,
alert delivery, and organizational controls, which are not supplied for verification.
Do not infer an actual deployment, traffic volume, compromise, or effective SCPs.
Review the submitted configuration and these requirements across all issue areas.
No customer-managed encryption key is required unless explicitly stated.
