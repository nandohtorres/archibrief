---
title: "ADR 0043: Auth Method Simplified — Email/Password Primary, Emailed Auth Code as Second Factor"
type: decision
tags: [adr, project, work-project, archibrief, security]
created: "2026-09-04"
updated: "2026-09-04"
status: accepted
---

# ADR 0043: Auth Method Simplified — Email/Password Primary, Emailed Auth Code as Second Factor

**Status:** Accepted (2026-09-04) — **supersedes the auth-method framing in
[ADR-0029](Work-Project-ADR-0029-Cognito-OTP-And-Guest-Caching.md)**: guest-mode
caching and the "no magic link" correction in ADR-0029 both stand
unchanged; only the passkey-primary decision is replaced. **Entirely
superseded by
[ADR-0044](Work-Project-ADR-0044-No-User-Accounts-Admin-Pre-Shared-Credential.md)**
(2026-09-11): no user accounts, so no sign-in method is needed at all.

## Context

ADR-0029 locked passkeys/WebAuthn as the preferred high-assurance primary
sign-in method, with email OTP as a fallback. Fernando confirmed
2026-09-04 he wants the simpler, more familiar path instead: standard
email + password as the primary login, with an emailed one-time auth code
as an added layer on top — explicitly deferring further detail (exact
MFA enforcement policy, whether/when passkeys get added later) until
build time, rather than deciding it all now.

## Decision

- **Primary sign-in: email + password**, via a Cognito user pool.
  Standard password policy (length/complexity per Cognito defaults or a
  slightly stricter custom policy — exact rules deferred to build time).
- **Second factor: an emailed one-time auth code** (Cognito email OTP as
  MFA/verification step on top of the password) — not the primary
  sign-in method itself, unlike ADR-0029's original framing.
- Passkeys/WebAuthn are **not** part of the v1 build. Not rejected
  outright — may be added later as an additional sign-in option if
  Fernando wants it post-v1, but it's no longer a planned v1 deliverable.
- Exact enforcement (is the emailed code required on every login, only
  new devices, only sensitive actions like admin operations) is
  explicitly **not decided here** — deferred to build time per
  Fernando's own framing ("if later we need more detail we will handle
  it once we get there").

## Consequences

- Meaningfully simpler to build than passkey/WebAuthn registration and
  relying-party-domain planning (ADR-0029's "plan the relying-party
  domain early" concern no longer applies to v1).
- Updates the project spec's v1 scope bullet,
  the build plan's Phase 6 auth step, and
  the private research notes on auth providers.
- Still uses Cognito (ADR-0018 stands) and still avoids a magic-link flow
  (ADR-0029's correction stands) — this ADR only changes which method is
  primary vs. secondary.

## Full reasoning

Fernando, directly, 2026-09-04: "i wana have normal login with email and
password and then sure we can add a auth key to email, thats what we
decide rn but if alter we need more detial we will handle it once we get
there."
