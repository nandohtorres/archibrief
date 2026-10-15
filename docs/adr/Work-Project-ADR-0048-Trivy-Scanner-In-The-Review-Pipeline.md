---
title: "ADR 0048: Trivy as the Deterministic Core, Run in Its Own Lambda"
type: decision
tags: [adr, project, work-project, archibrief, security, rule-engine]
created: "2026-10-15"
updated: "2026-10-15"
status: accepted
---

# ADR 0048: Trivy as the Deterministic Core, Run in Its Own Lambda

**Status:** Accepted (2026-10-15). Decided by Fernando. Covers master-list
items #12–#15.

## Context

The adversarial trap suite (2026-10-15) found ArchiBrief's own rule engine:

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
5. **Resource names are capped and cleaned (#14).** Names are part of the
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
- **One-time setup by Fernando:**
  - a deploy-role IAM addition for Lambda layers (`lambda:PublishLayerVersion`,
    `GetLayerVersion`, `DeleteLayerVersion` and `ListLayerVersions` on
    `layer:archibrief-dev-*`);
  - building the layer;
  - `terraform apply`. Done 2026-10-15. The first apply stopped at
    publishing the layer: pinning `s3_object_version` needs
    `s3:GetObjectVersion`, which the deploy role lacks. Fixed in Terraform
    rather than IAM, because the pin added nothing: Lambda copies the zip
    when it publishes, so a layer version never changes. The layer now
    republishes on `source_code_hash`. The zip upload uses `source_hash`,
    because a multipart upload's S3 etag never matches the file's MD5.
- **Accepted findings on our own infra,** recorded in `.trivyignore`:
  - SSE-S3 instead of customer-managed KMS keys;
  - the unencrypted budget-alert SNS topic, which AWS Budgets requires;
  - no WAF yet, which is planned in Phase 3.
- **Trivy can also scan for secrets,** which would cover master-list #19
  (secret scan on uploads) with the same layer. Not enabled yet.

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
