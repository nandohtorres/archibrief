---
title: "ADR 0029: Cognito OTP Correction and Guest Response Caching"
type: decision
tags: [adr, project, work-project, archibrief, security]
created: "2026-09-03"
updated: "2026-09-03"
status: accepted
---

# ADR 0029: Cognito OTP Correction and Guest Response Caching

**Status:** Accepted (2026-09-03) — **extends** ADR-0010, corrects
terminology, doesn't reverse the core decision. **Auth-method framing
superseded by
[[Work-Project-ADR-0043-Auth-Method-Simplified-Password-Plus-Email-Code]]**
(2026-09-04): the "no magic link" OTP correction and the guest-caching
decision below both stand; passkeys-as-primary was replaced with
email/password-primary + emailed auth code as a second factor. **The
auth-method question is now moot: superseded by
[[Work-Project-ADR-0044-No-User-Accounts-Admin-Pre-Shared-Credential]]**
(2026-09-11), which removes user accounts entirely. This ADR's
guest-caching *principle* (serve a precomputed/cached report, don't run
the pipeline fresh per visitor) carries forward unchanged into ADR-0044,
now applied to the only public-facing path rather than as an
anonymous-user special case.

## Context

Verified directly against AWS's own Cognito documentation: Cognito does
not offer an emailed "magic-link" flow — its passwordless option is email/
SMS **one-time password (OTP)**, or passkeys. ADR-0010's "magic-link
fallback" language was inaccurate. Codex separately flagged that the
guest/demo mode (fixed reference fixture) pays for a fresh agent run per
visitor even though the input is identical every time.

## Decision

- Passwordless fallback is **email OTP**, not a magic link (a true magic
  link would require a custom auth challenge and its own token/link
  lifecycle — not worth building for this use case).
- Passkeys as the preferred high-assurance path; plan the relying-party
  domain early (changing it forces users to re-register passkeys).
- Guest/demo mode serves a **precomputed or cached** report for the fixed
  reference fixture rather than running the full pipeline fresh per
  visitor. If bounded parameters are ever allowed, key the cache by the
  normalized parameter set.

## Consequences

- No change to the two-path (real account + guest) structure locked in
  ADR-0010.
- The caching change materially reduces guest-mode cost/abuse exposure,
  reinforcing ADR-0030.

## Full reasoning

See [[Work-Project-ADR-Review-Codex]] §"ADR-0010" and the direct AWS
Cognito documentation verification performed 2026-09-03.
