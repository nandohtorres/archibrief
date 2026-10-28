# Frontend CD verification — 2026-10-27

Branch: `feat/frontend-cd`, created from fetched `origin/master` at
`f13a535bcdb26f3dabdfd61749af2cd3547b8b56`. The clean, unpushed
`fix/report-header-and-workspace-polish` branch was preserved separately.

## Completed locally

| Check | Result |
|---|---|
| `npm ci` in frontend | Passed; lockfile unchanged |
| `npm run lint` | Passed |
| `npm run typecheck` | Passed |
| `npm run format:check` | Passed; generated next-env.d.ts is now excluded |
| `npm test` | 88 passed |
| `npm run test:tooling` | 11 passed, including GET-only smoke, stale-revision retries, timeout/failure cases and separate-checkout metadata |
| `npm run build` | Static export and build-info postbuild passed with local fonts |
| `npm run test:e2e` | 78 passed, including mocked public/deeper/chat paths, accessibility and viewports |
| Backend Ruff format/check | Passed, using the locked CI dependencies |
| Backend `pytest -m "not coverage_gap" --cov=backend --cov-report=term-missing` | 1,258 passed; 26 deselected; 89% total coverage |
| Trivy 0.76.0 infra scan, HIGH/CRITICAL, existing ignore file | Passed; no new exceptions |
| Terraform 1.9.8 `fmt -check -recursive infra` | Passed |
| Terraform 1.9.8 `validate` in infra/environments/dev | Passed, with existing provider deprecation warnings |
| actionlint 1.7.12 on both new workflows | Passed |
| Git Bash `-n scripts/deploy_frontend.sh` | Passed; the deployment script was not executed |
| Font integrity | All 14 WOFF2 files match the recorded upstream hashes; three original OFL licenses included |
| Google font dependency | No next/font/google import in layout; no fonts.googleapis.com/fonts.gstatic.com references in exported HTML/CSS; normal build succeeded using local files |
| Commit hooks | Gitleaks checks run on local commits; the infra commit also runs the existing Trivy hook |

Node was 24.14.0. Backend tests used a separate ignored build-directory
environment with CPython 3.12.15 and `backend/dev-requirements.lock.txt`, dummy
AWS credentials, metadata disabled and the pinned Trivy version. The existing
Python environment was not changed. Tests were run on Windows; CI runs Ubuntu.
The installed Terraform 1.15.8 also validated successfully; 1.9.8 was downloaded
with an official SHA-256 check to verify CI's 1.9 series specifically.

## One read-only production run

Command:

```text
node scripts/smoke_live.mjs https://archibrief.dev https://api.archibrief.dev
```

Actual output, exit code 0:

```text
PASS homepage and security headers: 200; ArchiBrief title; CSP, HSTS, frame, content-type and referrer protections
PASS build revision: valid metadata; revision unrecorded (manual build)
PASS site icon: 200; SVG available
PASS demo asset: 200; demo report JSON available
PASS API missing review: 404; get_review returned review not found
```

No expected revision was supplied: today's manual build reports null. The
automated release path supplies the tested SHA and requires an exact match.
No production POST, upload, review, deeper-review or chat request was sent.

## Limits and remaining owner work

- No Terraform plan/apply, AWS mutation, deployment, GitHub configuration, push
  or PR creation was performed. The OIDC exchange and actual automated S3/CDN
  publish still require the owner setup in [frontend-deployment.md](frontend-deployment.md).
- Terraform's existing `aws_region.name` and DynamoDB `hash_key` deprecation
  warnings remain. They do not prevent validation.
- `npm ci`/audit reports an existing moderate `fast-uri@3.1.8` advisory group
  through development-only `serve` → `ajv`. This branch does not change the
  lockfile or runtime dependencies. Track a separate development dependency
  update; this is not evidence of a clean dependency audit.
- Original third-party license texts retain upstream whitespace. Any
  `git diff --check` trailing-space notices in those OFL files are upstream
  license bytes; newly authored code/docs have no whitespace errors.
- Both workflows always use read-only smoke; the daily run has no AWS
  credentials. The CD role only publishes frontend files and invalidates one
  distribution. Backend deploys and paid model evaluations remain separate.


## Follow-up guided setup

GitHub API inspection found immutable OIDC subjects enabled on this repository.
The original name-only trust subject would not authenticate it. Terraform now
accepts a verified optional github_oidc_subject_prefix, validates its repository
name, and appends the fixed production environment suffix. Legacy repositories
retain the original default. The real prefix is stored only in ignored tfvars.

GitHub production and its master-only branch rule were created. Six public
repository variables were copied from the existing deployment settings and
verified. AWS_DEPLOY_ROLE_ARN remains pending the owner's apply. Local tfvars
was prepared with provider opt-in true. No AWS write, plan/apply or push ran.
The deploy SSO session is active; IAM ListPolicies was denied, so permission-set
changes remain an owner-admin console task. Terraform 1.9.8 validation passed
again after the subject correction, with the same deprecation warnings.
