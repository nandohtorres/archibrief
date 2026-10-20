# ADR 0010: Auth and Demo Access

**Status:** Accepted (2026-09-02) — **extended/corrected by
[ADR-0029](0029-cognito-otp-and-guest-caching.md)** (2026-09-03):
the two-path (real account + guest) structure stands; this ADR's
"magic-link" language was inaccurate (Cognito's passwordless fallback is
email/SMS OTP), and guest/demo mode now serves a precomputed/cached
report rather than a fresh pipeline run per visitor. **Primary sign-in
method further simplified by
[ADR-0043](0043-auth-method-simplified-password-plus-email-code.md)**
(2026-09-04): email/password primary + emailed auth code as a second
factor, passkeys deferred past v1. **Entirely superseded by
[ADR-0044](0044-no-user-accounts-admin-pre-shared-credential.md)**
(2026-09-11): no user accounts at all; single admin pre-shared
credential + fully static guest mode.

## Context

The goal was both real, genuinely implemented auth and frictionless
access for first-time visitors — these aren't mutually exclusive if
designed together.

## Decision

**Real accounts** (WebAuthn/passkey primary, email magic-link fallback —
the 2026 SaaS-auth baseline) as the primary path, **plus a no-signup
guest mode**: 1 free use, then prompted to create an account for 5 more.
Guest mode is scoped to the reference demo Terraform example (part of
the v1 scope) rather than arbitrary user-submitted input, to control
cost/abuse on the unauthenticated path.

## Consequences

- Real auth work is substantive security engineering, not just a login
  form.
- Guest-mode scoping ties directly into ADR-0011's rate-limiting/cost
  requirements.
- Specific provider (Cognito vs. Auth0 vs. custom) remains open.
