---
title: "ADR 0042: Minor Amendments Batch (ADR-0003, 0004, 0006, 0007, 0008, 0009, 0015, 0016, 0018, 0025)"
type: decision
tags: [adr, project, work-project, archibrief]
created: "2026-09-03"
updated: "2026-09-03"
status: accepted
---

# ADR 0042: Minor Amendments Batch

**Status:** Accepted (2026-09-03) — **extends** the listed ADRs; none of
the underlying decisions reverse

Small, additive corrections from an independent design review that
add detail without changing any core decision. Batched into one file
since none is substantial enough alone to warrant its own ADR.

- **ADR-0003 (framework mapping):** for observable AWS-configuration
  findings specifically, order as: (1) AWS Well-Architected, (2) AWS
  Foundational Security Best Practices/Security Hub when directly
  applicable, (3) CIS AWS Foundations Benchmark when directly applicable,
  (4) CIS Controls/NIST CSF as the higher-level cross-reference. More
  precise AWS-specific ordering; does not add SOC 2/ISO 27001/NIST 800-53
  scope.
- **ADR-0004 (Terraform):** pin the Terraform CLI/provider constraints
  and commit `.terraform.lock.hcl` for ArchiBrief's own infrastructure.
  For user submissions, report declared Terraform/provider versions and
  lock-file presence as evidence, don't trust/install them. Document
  which language constructs the static analyzer supports so unsupported
  constructs become `not-observable`, not silent false negatives.
- **ADR-0006 (Bedrock provider):** narrow "same model weights/outputs"
  to a defined domain contract (messages, structured result, usage,
  model/version, stop reason, normalized errors) rather than claiming
  full feature interchangeability. Pin the deployed model ID and store it
  with every report. Explicitly select a geographic (not global)
  cross-region inference profile when a preflight answer indicates data
  residency matters.
- **ADR-0007 (S3 Vectors):** use ordinary S3 as the immutable
  source-of-truth for normalized documents; S3 Vectors is a rebuildable
  index on top, not the source of truth itself. Choose non-filterable
  metadata keys, index dimension, and distance metric deliberately —
  they're immutable after index creation.
- **ADR-0009 (Python):** use a supported Lambda/AgentCore runtime, strict
  type checking, a formatter/linter, and one schema definition for the
  typed evidence ledger (already reflected in
  the coding conventions's pydantic-model requirement).
- **ADR-0015 (secrets/public repo):** broaden the denylist to
  `*.tfstate*`, saved plan files, `.terraform/`, crash logs, local
  overrides, backend configuration, and uploaded test repositories.
  Enable GitHub secret scanning/push protection alongside local/CI
  gitleaks. Test the CI gate with an inert detector value; document
  secret rotation/removal response.
- **ADR-0016 (Next.js):** default to static/client rendering for
  dashboard surfaces with the authenticated API as the security boundary;
  add a Next.js server/BFF only when a concrete requirement justifies the
  extra runtime/cookie/deployment surface.
- **ADR-0018 (Cognito):** use a user pool for authentication/OAuth-OIDC
  tokens/group claims; have the backend validate the access token and
  enforce app roles server-side. Don't issue AWS credentials through an
  identity pool unless an actual direct-to-AWS user flow requires it —
  this demonstrates Cognito/OIDC/JWT/RBAC integration cleanly, which is a
  strength, not a lesser version of the skill.
- **ADR-0025 (diagram tooling):** the recognized skill is architecture
  communication and AWS judgment, not the specific library — temper any
  resume claim accordingly. Manually review generated diagrams for
  legibility/trust-boundaries/data-flow accuracy. Don't treat
  `mingrammer/diagrams` as a head start on the future in-app diagram
  feature — that feature needs a safe intermediate representation of
  untrusted Terraform, a different concern from curated documentation
  diagrams.

## Full reasoning

See an independent design review, respective sections per ADR
number above.
