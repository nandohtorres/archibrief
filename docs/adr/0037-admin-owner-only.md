# ADR 0037: Admin Role Restricted to the Project Owner; Scoped Reviewer Role for Invited Reviewers

**Status:** Accepted (2026-09-03) — **supersedes** ADR-0021's proposal to
grant `admin` to external reviewers. **Amended by
[ADR-0044](0044-no-user-accounts-admin-pre-shared-credential.md)**
(2026-09-11): the owner-only admin *principle* carries forward
unchanged, but the mechanism changes from a Cognito RBAC role to a single
pre-shared credential (there are no user accounts to have roles at all).

> **Superseded (2026-10-23):** the admin key was removed when public submissions opened. Everyone, the owner included, now uses the public path and limits; see [ADR-0046's addendum](0046-public-reviews-and-grounded-chat.md#addendum-2026-10-23-what-the-release-actually-uses).
The `reviewer`/`demo` role for invited reviewers below is **cut, not deferred**
— see ADR-0044.

## Context

ADR-0021 proposed possibly granting the app's `admin` role to interested
external reviewers for expanded exploration. A design review flagged this
as a real least-privilege violation: `admin` is the application's single
highest-privilege role, and granting it to people outside the owner's
control creates real exposure (visibility into other users' data,
billing, roles) that doesn't actually serve the underlying goal any
better than a scoped role would. Not urgent; can be implemented later.

## Decision

- `admin` role stays **owner-only**, granted through an out-of-band,
  audited privileged operation (Terraform bootstrap or a break-glass AWS
  CLI/console procedure) — never an in-app self-service endpoint.
- A separate, constrained `reviewer`/`demo` role is added later (not
  urgent, deferred past initial build) for invited reviewers who want expanded
  access: sanitized fixtures only, larger bounded quotas or feature
  visibility, no access to other users' data, billing, roles, or system
  configuration. Time-bound invitations preferred over persistent
  elevated accounts.

## Consequences

- Updates ADR-0021's RBAC model — two tiers (standard/admin) becomes
  three (standard/reviewer/admin) once the reviewer role is built, admin
  narrowed to owner-only immediately.
- No urgency to build the reviewer role before other v1 work — explicitly
  deferrable.
