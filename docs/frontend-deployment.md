# Frontend delivery and live smoke

Infrastructure changes are owner-operated. The workflows publish frontend
files only; they never run Terraform, deploy Lambdas or start a paid review.

## How CD works

`deploy-frontend.yml` runs after the `ci` workflow **succeeds on a push to master**.
It ignores PR CI runs, forks and failed CI. Every successful master run deploys,
including docs-only changes: this deliberately avoids a fragile changed-path or
previous-deployment comparison. CI remains the merge gate.

The release checkout uses `workflow_run.head_sha`, not the latest master tip.
Trusted automation is checked out separately: the tested commit for automatic
runs, and the current workflow revision for manual dispatch. Rolling back does
not require an old commit to contain today's smoke script. Manual dispatch
must run the workflow from master; its `ref` input accepts master or a full
lowercase SHA that is an ancestor of master. Use a previously successful release
for rollback. Manual dispatch is an explicit operator release, not another CI run.

Node 24 installs the release's locked frontend dependencies. Public build
variables become its ignored `.env.production.local`. OIDC supplies short-lived
AWS credentials for `archibrief-dev-ci-deploy`. The existing
`scripts/deploy_frontend.sh` builds that checkout, refreshes its build metadata,
syncs hashed assets with immutable caching, syncs other files without deleting
old hashed chunks, and invalidates `/*`. Its optional `FRONTEND_DIR` selects the
release checkout; ordinary manual calls need no change.

The deploy role only lists the one frontend bucket, writes/deletes its objects,
and creates/reads invalidations for the one CloudFront distribution. It has no
Terraform, IAM, backend deployment or paid API permissions. No long-lived AWS
secret is stored in GitHub. All actions are SHA-pinned with release tags noted.

The final smoke waits up to about three minutes for build-info.json to report
the release SHA. The job summary records the SHA, publish result, invalidation
ID, and each smoke result. `deploy-frontend-production` concurrency prevents
simultaneous deploys; `cancel-in-progress: false` lets an active deployment
finish. GitHub concurrency is not a FIFO queue and can replace a pending run.
Do not queue a rollback while newer automatic releases are pending.

## Owner setup checklist

1. **Update the deployment permission set manually.**
   [frontend-cd-permissions.json](frontend-cd-permissions.json) contains the exact
   additive JSON statements, with `<ACCOUNT_ID>` placeholders. Substitute the
   real account only in the AWS console or ignored local files. These grant
   lifecycle/read/tag access to the exact GitHub OIDC provider, creation of the
   exact CI role without a runtime boundary, and its trust/tag updates. The
   existing `IamRolesScopedToProjectPrefix` statement already grants the role's
   get/delete/tag and inline-policy operations. The inline policy needs no new
   managed-policy attachment grant. The gitignored proposed
   `04-iam-self-management.json` and its README have also been updated locally;
   01–03 and 05 need no new CD permissions. Update the corresponding
   customer-managed policy, then reprovision `ArchiBriefDeploy` in IAM Identity
   Center. Existing runtime boundary requirements and deny rules stay intact.
2. **Review and apply Terraform yourself.** In the ignored
   `infra/environments/dev/terraform.tfvars`, set:

   ```hcl
   create_github_oidc_provider = true
   github_oidc_provider_arn   = null
   github_repo                = "nandohtorres/archibrief"
   ```

   From `infra/environments/dev`, using your authenticated deploy profile:

   ```bash
   export AWS_PROFILE=archibrief-deploy
   mkdir -p tmp
   terraform plan -out=tmp/cd.tfplan
   terraform apply tmp/cd.tfplan
   terraform output -raw ci_deploy_role_arn
   ```

   Review the saved plan before applying; these commands are for Fernando,
   and were not run by the coding agent. The new flag defaults to false. If an
   account-wide GitHub provider already exists, leave the flag false and set
   its ARN in the ignored tfvars instead of creating a duplicate. When true,
   the module uses the newly managed provider in preference to an external ARN.
3. **Create GitHub Environment `production`.** Under repository Settings →
   Environments, use **Selected branches and tags**, allow the branch `master`,
   and allow no tags. This is required: the exact OIDC subject is
   `repo:nandohtorres/archibrief:environment:production`, which identifies the
   environment rather than the branch. Environment branch rules plus workflow
   checks enforce master. Keep required CI checks on master. Optional required
   reviewers add an approval gate if desired. The trust subject is built from
   `github_repo`, with no literal account values in Terraform source.
4. **Set GitHub repository Actions variables** (not secrets):

   | Variable | Value/source |
   |---|---|
   | `AWS_DEPLOY_ROLE_ARN` | `terraform output -raw ci_deploy_role_arn`; copy directly to GitHub, not a tracked file |
   | `AWS_REGION` | `us-east-1` |
   | `FRONTEND_BUCKET` | `terraform output -raw frontend_bucket_name`; currently `archibrief-dev-frontend` |
   | `DISTRIBUTION_ID` | `terraform output -raw frontend_distribution_id`; currently `E3TWWLCX3SIZIP` |
   | `NEXT_PUBLIC_API_BASE_URL` | `https://api.archibrief.dev` |
   | `NEXT_PUBLIC_PUBLIC_ACCESS_ENABLED` | Copy the intended public-access flag from the current ignored `.env.production.local` (`true` or `false`); this does not enable the backend by itself |
   | `NEXT_PUBLIC_TURNSTILE_SITE_KEY` | The existing public Turnstile site key from Cloudflare/current ignored frontend env file; never use the secret key |

   All three public build settings must be present. The workflow fails on a
   missing setting or invalid boolean instead of silently publishing fixture
   mode or a broken public submission form.
5. **Push the local branch yourself**, open a PR, merge after CI, then watch
   `deploy-frontend` and its summary. No push or AWS mutation was performed by
   the coding agent. The unrelated local
   `fix/report-header-and-workspace-polish` branch is preserved separately and
   is not included in this branch; publish it separately when ready.

## Rollback

Open Actions → deploy-frontend → Run workflow. Keep the workflow branch set to
`master` and set **ref** to the full SHA of the prior known-good master release.
The same environment restrictions, deployment script and live SHA check apply.
This republishes the older frontend; it does not revert Git history or backend
infrastructure. Review compatibility with the current backend before choosing
the commit. A revision from before local fonts may still need Google at build
time. A failed publish/smoke is not rolled back automatically; inspect its
summary and dispatch a known-good SHA.

You may re-run a successful automatic deployment run to republish its original
tested SHA. Prefer explicit manual dispatch for choosing a different revision.

## Read-only smoke and daily checks

```bash
node scripts/smoke_live.mjs https://archibrief.dev https://api.archibrief.dev
# Optional deployment provenance check:
node scripts/smoke_live.mjs https://archibrief.dev https://api.archibrief.dev <full-sha>
# Or, from frontend/:
npm run smoke:live -- https://archibrief.dev https://api.archibrief.dev
```

The five checks require a homepage 200 and ArchiBrief title, the Terraform
security-header protections, valid build metadata, an SVG icon, a demo report
JSON, and the get_review Lambda's exact missing-review 404 JSON. A gateway error,
403, 5xx or timeout fails. All requests use GET, a ten-second timeout, no
redirects and the site's Origin. No uploads, review submissions, deeper review
or chat calls are made. Without an expected SHA, a valid manual build with a
null revision is accepted. With a SHA, stale/temporarily unavailable metadata
retries with backoff for roughly three minutes, then fails if it still differs.
One PASS/FAIL line is printed per check; any failure exits nonzero.

`smoke.yml` runs daily at **12:23 UTC** and on manual dispatch. It needs no AWS
credentials, browser, dependency installation or production writes. Failures use
GitHub's normal Actions notifications; enable failed-workflow email in your
GitHub notification settings. Each run also writes a smoke summary.

## Manual deployment fallback

Keep `frontend/.env.production.local` configured locally, install frontend
dependencies, authenticate your existing SSO profile, then from the repo root:

```bash
FRONTEND_BUCKET=archibrief-dev-frontend \
DISTRIBUTION_ID=E3TWWLCX3SIZIP \
AWS_PROFILE=archibrief-deploy \
ARCHIBRIEF_BUILD_REVISION=$(git rev-parse HEAD) \
  bash scripts/deploy_frontend.sh
node scripts/smoke_live.mjs https://archibrief.dev https://api.archibrief.dev "$(git rev-parse HEAD)"
```

Use a clean checkout for revision provenance. The script is the same one CD
uses; cache policy, old-chunk preservation and invalidation stay in one place.

## Fonts and verification limits

Fonts now use `next/font/local`, retaining existing CSS variables, weights and
styles. Upstream release URLs, original OFL licenses and per-file hashes are in
[the font directory](../frontend/app/fonts/README.md). Normal builds no longer
fetch fonts.googleapis.com or fonts.gstatic.com. Terraform also removes those
unneeded font/style CSP origins when the owner applies it.

The deployment workflows and OIDC exchange cannot be exercised end-to-end until
the owner applies infrastructure, configures GitHub and pushes/merges. Terraform
validation is not a deployment test; no plan or apply was run. Local test results
and the one read-only production run are recorded in
[frontend-cd-verification.md](frontend-cd-verification.md).

References: [GitHub OIDC/AWS and environment restrictions](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws),
[AWS provider OIDC resource](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_openid_connect_provider).
