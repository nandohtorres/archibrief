---
title: "ADR 0044: No User Accounts — Single Admin Pre-Shared Credential; Guest Mode Fully Static"
type: decision
tags: [adr, project, work-project, archibrief, security]
created: "2026-09-11"
updated: "2026-09-11"
status: accepted
---

# ADR 0044: No User Accounts — Single Admin Pre-Shared Credential; Guest Mode Fully Static

**Status:** Accepted (2026-09-11) — **supersedes
[ADR-0010](Work-Project-ADR-0010-Auth-And-Demo-Access.md),
[ADR-0018](Work-Project-ADR-0018-Auth-Provider-Cognito.md),
[ADR-0029](Work-Project-ADR-0029-Cognito-OTP-And-Guest-Caching.md) (auth-method
portion; guest-caching *principle* carries forward, restated below),
[ADR-0043](Work-Project-ADR-0043-Auth-Method-Simplified-Password-Plus-Email-Code.md),
and the `reviewer`/`admin` RBAC tiering in
[ADR-0021](Work-Project-ADR-0021-IAM-Model-And-App-RBAC.md) /
[ADR-0037](Work-Project-ADR-0037-Admin-Fernando-Only.md)**.

## Context

Fernando reassessed the product's actual purpose 2026-09-11: ArchiBrief
exists to demonstrate the ability to design and build a real,
security-conscious AWS system — not to be a multi-tenant SaaS product
today. A real user-accounts system (Cognito user pool, MFA, SES-backed
email, signup/login UI, per-user RBAC tiers) was consuming real build
time and carrying a real external dependency (SES domain verification +
AWS production-access approval, both with unbounded wait time) without
adding proportional value to the actual goal: getting a working, honest
system in front of real users quickly. The security depth a login system
would add (AWS-native identity, IAM) is already present elsewhere in the
build — per-Lambda least-privilege IAM, Bedrock Guardrails, the RAG
pipeline, Step Functions orchestration.

Separately, Fernando raised the real follow-on question: without
accounts, what stops abuse/cost-farming by anonymous visitors (IP
rotation, bots)? Resolved by recognizing the two concerns don't require
the same fix — the abuse-surface risk is really about the *expensive*
pipeline-submission endpoint being publicly reachable at all, not about
whether visitors have accounts.

## Decision

- **No user accounts, no Cognito, no signup/login UI, no app-level RBAC
  tiers** (`standard`/`reviewer`/`admin` collapses to nothing — there is
  no logged-in user concept at all).
- **The live review-submission pipeline is gated behind a single
  pre-shared admin credential** (a static secret, checked via an API
  Gateway Lambda authorizer or native API-key + usage plan; secret lives
  in AWS Secrets Manager / SSM Parameter Store, never in source). This
  replaces Cognito entirely for the one person (Fernando) who needs to
  actually run reviews. The frontend exposes a minimal "enter admin key"
  field; the key is held client-side (e.g. `localStorage`) and sent as a
  request header. No password reset, no MFA, no session lifecycle to
  build or test.
- **Guest/demo mode becomes the only public-facing path**, and it is
  fully static: one or more real reviews are run once (by Fernando, via
  the admin-gated path) against realistic sample Terraform, and the best
  result is served as a precomputed report to any visitor — no live
  pipeline invocation, no Bedrock/Titan calls, no marginal cost per
  visitor. This is the same caching principle ADR-0029 established for
  guest mode; it now applies universally rather than as an
  anonymous-user special case, because there is no other kind of
  public-facing case anymore.
- **The `reviewer`/`demo` role from ADR-0037 is cut, not deferred.**
  There is no in-app elevated-access mechanism for external reviewers.
  An external reviewer who wants to see the system run live gets
  that through the admin-gated path handed to them directly by Fernando
  (or a recorded demo video, already planned) — not a self-service role.
- **Abuse/cost protection is reframed, not dropped**, per
  [ADR-0030](Work-Project-ADR-0030-Rate-Limiting-Reframed.md): defense-in-depth
  moves to protecting the one gated endpoint (API Gateway usage
  plan/throttling, an AWS WAF rate-based rule, Lambda reserved
  concurrency, and — the real backstop — a hard AWS Budget alarm wired to
  a tested kill switch) rather than building per-user counters that no
  longer have a user to key off of. The public guest path needs no
  abuse protection beyond normal static-content serving, since it never
  touches the paid pipeline.

## Consequences

- **Removes the SES dependency entirely** — the pending SES setup becomes
  moot, not just deferred; there is no email-based MFA to re-enable
  because there is no login.
- **Infra:** `infra/modules/auth/` (Cognito user pool/client/domain) is
  removed from the Terraform root module; the API Gateway authorizer
  changes from Cognito JWT to a single pre-shared-secret check. This is
  a real infra change against already-applied resources — Fernando runs
  `terraform plan`/`apply` (and the Cognito resource destroy) himself;
  automation never applies infrastructure.
- **Backend:** the `Users` DynamoDB table and any per-user ownership
  checks are dropped; `GuestSessions` (if kept) becomes purely a
  rate-limiting/session-scoping construct for the gated admin path, not
  an identity table.
- **Frontend:** no login/signup screens to build (none existed yet per
  the current build, so this is scope *avoided*, not code to delete);
  add the minimal admin-key entry field instead.
- **Test surface shrinks:** no cross-user access tests, no
  session/token/password-reset tests needed in the adversarial
  regression suite (ADR-0038) or Phase 7 E2E coverage — replaced by
  tests that the gated endpoint actually rejects an unauthenticated or
  wrong-key request.
- **Threat model (ADR-0041)** must reflect the simplified trust
  boundary: one shared operator secret rather than per-user identity —
  this should be stated explicitly as a deliberate, right-sized decision
  for a single-operator demo, not an oversight — documenting the real
  tradeoff honestly.
- Updates required in the project spec (v1 scope, application
  authorization section), the system design notes (architecture
  diagram, RBAC section, DynamoDB Users table, API auth routes),
  the build plan (Phase 1 Terraform module list, Phase 6 —
  effectively replaced by a much smaller "admin gate" step), and
  the deployment roadmap (Cognito line, SES TODO removed).

## Full reasoning

Fernando, directly, 2026-09-11: reassessed whether a user base adds
value to "the message we're trying to send and prove," concluded it's
"extra work... for no reason" relative to demonstrating the core
pipeline, while still wanting to "hit on all the bells and whistles" that
matter for the roles being targeted (Solutions Architect / security /
platform engineering-adjacent). Full exchange in this session's
conversation log.
