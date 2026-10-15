---
title: "ADR 0015: Public Repo Strategy and Secrets Handling"
type: decision
tags: [adr, project, work-project, archibrief, security]
created: "2026-09-03"
updated: "2026-09-03"
status: accepted
---

# ADR 0015: Public Repo Strategy and Secrets Handling

**Status:** Accepted (2026-09-03) — **amended by
[ADR-0042](Work-Project-ADR-0042-Minor-Amendments-Batch.md)** (2026-09-03): the
one-real-repo strategy stands; broadens the secrets denylist and adds
GitHub secret scanning/push protection alongside local/CI gitleaks.

## Context

Project will be published publicly on GitHub so hiring managers can
review real code. Considered whether a separate "dummy"/skeleton repo
should sit alongside the real one to avoid exposing sensitive details.

## Decision

**One real public repo, no dummy repo.** A parallel sanitized decoy can
read as hiding something rather than as security discipline — a
correctly-secured real repo is itself more credible evidence. Standard
secret hygiene instead: no real credentials ever committed; real secrets
live in AWS Secrets Manager/SSM Parameter Store, referenced by name/ARN;
`.env.example` with placeholders, `.gitignore` covering all real
`.env`/`.tfvars`/credential files; pre-commit secret scanning (e.g.
gitleaks/git-secrets) as a real CI gate. Demo/example Terraform fixture
data uses sanitized generic values, never literal account IDs/ARNs from
Fernando's real AWS account.

## Consequences

- Reinforces the existing "security is a first-class feature" locked
  decision — proper secret hygiene in the one real repo already covers
  the underlying concern.
- Secret-scanning-as-CI-gate becomes another genuine, demonstrable
  security-practice talking point, folding into the already-required
  full CI/CD pipeline.

## Full reasoning

See conversation 2026-09-02/09-03 on file organization and public-repo
readiness (not yet copied into the project decision log narrative — flagged as a
to-do).
