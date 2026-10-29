# ADR 0055: Frontend Continuous Deployment Through a Scoped OIDC Role

**Status:** Accepted (2026-10-28, PR #45).

## Context

Each frontend release was a manual S3 sync and CloudFront invalidation from
the owner's SSO session. Merged frontend changes sat undeployed, and the
live site's revision wasn't recorded anywhere.

## Decision

1. **`deploy-frontend.yml`** runs after a successful `ci` run on `master`,
   builds that exact revision and publishes it with the existing deployment
   script, then checks the live build stamp and read-only API health.
2. **A frontend-only GitHub OIDC role** (`archibrief-dev-ci-deploy`) can
   only write the site bucket and invalidate its CloudFront distribution.
   Only a run in the `production` environment, restricted to `master`, can
   assume it (the immutable OIDC subject is checked).
3. **A daily smoke workflow** (`smoke.yml`, `scripts/smoke_live.mjs`) runs
   GET-only checks with no AWS credentials and no paid calls.
4. **Rollback** is a revert on `master`; its merge redeploys. The manual
   SSO path stays documented as a fallback.
5. **The backend is not deployed by CI.** The owner builds packages, reviews
   a `terraform plan` and applies it.

## Consequences

- Two merges in quick succession can deploy out of order. Rerun the
  workflow on `master` after the last one.
- `build-info.json` records the exact revision that is live.
- Owner setup, rollback and the fallback are in
  [frontend deployment](../frontend-deployment.md); verification in
  [frontend CD verification](../frontend-cd-verification.md).
