# frontend-hosting

Static hosting for `frontend/out` (S3 + CloudFront via OAC), served at the
default `*.cloudfront.net` domain and optionally at custom domains
(`aliases`/`certificate_arn`). The ACM certificate and its DNS validation
live in `infra/environments/dev/`, because they are shared with the
api-gateway module's custom domain. See that environment's README for the
apply sequence.

This module only provisions infrastructure. Frontend delivery uses the shared
`scripts/deploy_frontend.sh` script, either from GitHub Actions after successful
master CI or manually through the existing SSO deploy profile. It preserves old
hashed chunks, sets immutable caching on `_next/static`, syncs other files and
invalidates CloudFront. Do not replace it with a single blanket `sync --delete`.

See [frontend deployment](../../../docs/frontend-deployment.md) for the owner
setup checklist, GitHub variables, read-only smoke, rollback and manual fallback.
