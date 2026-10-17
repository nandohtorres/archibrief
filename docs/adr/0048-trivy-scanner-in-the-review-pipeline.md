# ADR 0048: Trivy as the Deterministic Core, Run in Its Own Lambda

**Status:** Accepted (2026-10-15).

## Context

The adversarial trap suite found that ArchiBrief's own rule engine:

- missed 14 of 14 sneaky-but-dangerous Terraform configs;
- wrongly flagged 3 of 4 safe ones.

Root causes:

- The parser keyed resources by bare name, so same-named resources in two
  modules overwrote each other.
- It dropped `data` blocks and `locals`.
- Rules compared raw strings, so they missed:
  - policies written with `jsonencode()`, heredocs or
    `aws_iam_policy_document`;
  - values hidden in variable defaults;
  - references through locals;
  - `count = 0`.

Trivy, an established open-source IaC scanner, caught 8 of 14 when run
locally. It evaluates variables, locals, `count` and modules properly. It
missed the IAM wildcard tricks and database ports open via the newer
ingress-rule resource.

Two jobs for Trivy were distinguished:

1. Checking ArchiBrief's own Terraform before commit or push: CI and
   pre-commit.
2. Checking visitors' Terraform at review time, as part of the product.

Job 2 has to run server-side, because visitors' code never goes through
our CI.

## Decision

1. **Trivy is the deterministic core**, with ArchiBrief's own rules for
   what it misses and as the fallback.
   - Only **16 trusted checks** are kept (`backend/shared/trivy_checks.py`).
     Noisy checks are dropped; "use a customer-managed KMS key" was trap
     f03's false positive.
   - Every kept check was seen firing on real Terraform here, and every
     Well-Architected ID was checked against the retrieval corpus.
   - When Trivy ran, it owns those concerns and ArchiBrief's rule for the
     same concern steps aside, so nothing is reported twice.
2. **Trivy runs in its own Scan Lambda, as a Lambda layer.**
   - The layer approach was chosen over a container-image Lambda: it reuses
     the existing zip packaging and needs no image registry.
   - A cluster (ECS/Fargate) or CodeBuild is overkill at our volume and
     slower to start.
   - The binary is pinned to Trivy 0.76.0 and checked against Aqua's
     published SHA-256 at build time.
   - **Size alarm:** the layer build fails above a 230 MiB budget for the
     Scan Lambda, ahead of Lambda's 250 MiB limit. Today it is 175 MiB.
     Past the budget, move the Scan Lambda to a container image (10 GB
     limit); only the packaging changes.
   - The layer zip is about 51 MB, over Lambda's 50 MB direct-upload limit,
     so it's published from a new private, encrypted, versioned
     `archibrief-dev-artifacts` bucket.
3. **Scanning is boxed in.** Found during the spike: Trivy downloads remote
   modules named in the submitted code, so a submitter could make the
   service fetch arbitrary URLs. Controls:
   - **Remote sources neutralized:** every `source = "..."` that isn't a
     local path inside the archive is rewritten before scanning.
   - **No credentials or network for Trivy:** it runs with a clean
     environment (no AWS credentials) and HTTP(S) proxies pointed at a
     closed local port.
   - **Its own Lambda,** with read-only access to `uploads/` and nothing
     else.
   - **Never fails a review:** the Lambda reports problems as
     "unavailable", and the state machine's Catch covers the Lambda itself
     failing. The review falls back to ArchiBrief's own rules and says the
     scanner didn't run.
   - This is the one documented exception to the "no subprocess on
     submitted content" rule. Trivy evaluates HCL statically and never
     runs terraform, providers or provisioners.
4. **ArchiBrief's own rules were rebuilt** so they hold up even when Trivy
   is unavailable:
   - The parser is module-aware and keeps `data` blocks and `locals`.
   - A resolver handles `jsonencode()`, heredocs, variable defaults, locals
     and policy documents.
   - `count = 0` resources are skipped.
   - Coverage now includes IAM wildcards in every policy form, sensitive
     ports open over IPv4 and IPv6 on all three ingress resource types,
     public bucket policies, half-disabled public access blocks and public
     RDS.
5. **Resource names are capped and cleaned.** Names are part of the
   model's input via rule findings, so they reach finding text only
   restricted to identifier characters and capped at 32 characters. The
   prompt already frames findings as untrusted data.
6. **Our own repo:**
   - CI installs the same pinned, checksum-verified Trivy, so the trap
     suite always runs its Trivy mode.
   - CI fails on HIGH/CRITICAL findings in `infra/` that aren't accepted,
     with a reason, in `.trivyignore`.
   - The pre-commit hook runs the same scan when a commit touches `infra/`.

## Consequences

- **Trap suite:**
  - 14/14 dangerous configs caught;
  - 0/4 red herrings flagged;
  - the injection payload is truncated.

  This holds both with ArchiBrief's own rules alone and with Trivy (was
  0/14 and 3/4).
- **Backend tests:** 377 pass, with no remaining expected failures.
- **Cost:** about $0.00005 of Lambda time per review, plus negligible S3
  storage.
- **Latency:** cold starts add a few seconds to the background pipeline;
  nobody waits on it synchronously.
- **One-time manual setup:**
  - a deploy-role IAM addition for Lambda layers (`lambda:PublishLayerVersion`,
    `GetLayerVersion`, `DeleteLayerVersion` and `ListLayerVersions` on
    `layer:archibrief-dev-*`);
  - building the layer;
  - `terraform apply`.
- **Layer publishing:** the layer republishes on `source_code_hash`
  instead of pinning `s3_object_version`. The pin would need
  `s3:GetObjectVersion`, which the deploy role lacks, and adds nothing:
  Lambda copies the zip when it publishes, so a layer version never
  changes. The zip upload uses `source_hash`, because a multipart
  upload's S3 etag never matches the file's MD5.
- **Accepted findings on our own infra,** recorded in `.trivyignore`:
  - SSE-S3 instead of customer-managed KMS keys;
  - the unencrypted budget-alert SNS topic, which AWS Budgets requires;
  - no WAF yet, which is planned for public submissions (ADR-0046 Phase 3).
- **Trivy can also scan for secrets,** which would cover the planned
  secret scan on uploads (ADR-0046 §6) with the same layer. Not enabled
  yet.

## Amendment (2026-10-15, later): credential-theft rules ArchiBrief owns

A free parse of the planned demo slices showed a gap. On Rhino Security
Labs' CloudGoat `cloud_breach_s3` (the attack path publicly reported for
the 2019 Capital One breach), the review caught the bucket issues but not
the cause: Trivy flagged IMDSv1 (AWS-0028), and nothing flagged the EC2
role's `AmazonS3FullAccess`.

**Decision:** two new ArchiBrief rules (`rule_engine@2026-10-15b`):
- `rule_ec2_imdsv2_required`: instances and launch templates whose
  `metadata_options.http_tokens` isn't `"required"`, unless the code
  requires IMDSv2 account-wide (`aws_ec2_instance_metadata_defaults`).
  When the instance's role is broad, the finding's risk text names the
  role and its policy, so the chain is in one finding and doesn't depend
  on the model joining two.
- `rule_compute_role_broad_managed_policy`: roles trusted by EC2,
  Lambda, ECS tasks or EKS pods with a broad AWS-managed policy
  (`AdministratorAccess`, `PowerUserAccess`, the named `*FullAccess`
  policies), attached any of the three ways. Unknown `*FullAccess` names
  are described generically, so a made-up name never reaches the model.
  Roles only people assume are out of scope (red herring f06).

**Why ArchiBrief owns IMDS instead of trusting AWS-0028:** Trivy can be
unavailable on a run, and the trusted-check path would make our rule
step aside, losing the linked role detail. AWS-0028 stays untrusted, so
there's exactly one IMDS finding either way.

**Tests:** traps t15, t16 (must flag) and f05, f06 (must not flag), in
both modes; 58 trap tests and 413 backend tests pass. On the CloudGoat
slice the review now reports both halves of the chain.

## Alternatives considered

- **Our own engine only, with Trivy in tests:** no infra change, but we'd
  maintain every check ourselves. Rejected: the proven tool already
  handles the hard part, evaluating Terraform.
- **Container-image Lambda now:** no size worry, but it needs an ECR
  repository, Docker build-and-push in deploys, and new ECR permissions.
  Kept as the next step if the size alarm trips.
- **Trivy inside the Ingest Lambda:** fewer moving parts, but Ingest holds
  S3 write and Guardrails permissions. Rejected for isolation.
- **Checkov:** comparable checks, but a much larger Python dependency tree
  to ship in a Lambda.
