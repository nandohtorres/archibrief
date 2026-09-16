---
title: "ADR 0010: Auth and Demo Access"
type: decision
tags: [adr, project, work-project, archibrief]
created: "2026-09-02"
updated: "2026-09-03"
status: accepted
---

# ADR 0010: Auth and Demo Access

**Status:** Accepted (2026-09-02) — **extended/corrected by
[[Work-Project-ADR-0029-Cognito-OTP-And-Guest-Caching]]** (2026-09-03):
the two-path (real account + guest) structure stands; this ADR's
"magic-link" language was inaccurate (Cognito's passwordless fallback is
email/SMS OTP), and guest/demo mode now serves a precomputed/cached
report rather than a fresh pipeline run per visitor. **Primary sign-in
method further simplified by
[[Work-Project-ADR-0043-Auth-Method-Simplified-Password-Plus-Email-Code]]**
(2026-09-04): email/password primary + emailed auth code as a second
factor, passkeys deferred past v1. **Entirely superseded by
[[Work-Project-ADR-0044-No-User-Accounts-Admin-Pre-Shared-Credential]]**
(2026-09-11): no user accounts at all; single admin pre-shared
credential + fully static guest mode.

## Context

Fernando wants both real, genuinely-implemented auth (demonstrates
skill) and frictionless access for recruiters reviewing the portfolio —
these aren't mutually exclusive if designed together.

## Decision

**Real accounts** (WebAuthn/passkey primary, email magic-link fallback —
the 2026 SaaS-auth baseline) as the primary path, **plus a no-signup
guest mode**: 1 free use, then prompted to create an account for 5 more.
Guest mode is scoped to the reference demo Terraform example (ADR, see
v1 scope in [[Work-Project-Spec]]) rather than arbitrary user-submitted
input, to control cost/abuse on the unauthenticated path.

## Consequences

- Real auth work is itself genuine resume-worthy security evidence, not
  just a login form.
- Guest-mode scoping ties directly into ADR-0011's rate-limiting/cost
  requirements.
- Specific provider (Cognito vs. Auth0 vs. custom) remains open.

## Full reasoning

See [[Work-Project]] §"W1-W4 stack research findings" and
[[Research-Work-Auth]].
