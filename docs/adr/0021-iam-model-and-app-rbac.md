# ADR 0021: IAM Model and Application-Level RBAC

**Status:** Accepted (2026-09-03) — **external-reviewer admin proposal superseded
by [ADR-0037](0037-admin-owner-only.md)** (2026-09-03): the
per-function IAM model stands; `admin` is now owner-only with a
separate constrained `reviewer` role for invited reviewers, added later. **The
application-RBAC portion (layer 2) is superseded by
[ADR-0044](0044-no-user-accounts-admin-pre-shared-credential.md)**
(2026-09-11): no user accounts, so no app-level roles at all — the
per-function AWS IAM model (layer 1) is unaffected and stands.

## Context

Two distinct concerns, deliberately kept separate per the existing
"application authorization is not AWS IAM" rule: (1) what AWS resources
each backend Lambda function can touch, and (2) what a logged-in human
user is allowed to do inside the app. An early proposal for an
"elevated IAM role for higher users" turned out to belong in layer 2,
not layer 1.

## Decision

**AWS IAM (backend):** one dedicated least-privilege IAM execution role
per Lambda function, never shared between functions, refined using IAM
Access Analyzer against real CloudTrail usage. Standard current AWS best
practice.

**Application-level RBAC (frontend/app):** at minimum two user roles —
`standard` and `admin`. Admin role is for the project owner's use
post-launch (full authorized access while recording demo videos) and
may later be selectively granted to invited reviewers who want to
explore beyond the standard/guest experience — exact grant mechanism
deferred, not yet designed.

## Consequences

- Two separate, real permission-control layers: per-function AWS IAM
  least-privilege, and application-level RBAC — genuinely different
  controls, both implemented.
- Admin-role grant mechanism (how an invited reviewer would actually receive
  elevated access) is an open implementation detail, not yet decided.
