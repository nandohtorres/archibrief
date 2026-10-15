---
title: "ADR 0037: Admin Role Restricted to Fernando; Reviewer Role for Recruiters"
type: decision
tags: [adr, project, work-project, archibrief, security]
created: "2026-09-03"
updated: "2026-09-03"
status: accepted
---

# ADR 0037: Admin Role Restricted to Fernando; Reviewer Role for Recruiters

**Status:** Accepted (2026-09-03) — **supersedes** ADR-0021's proposal to
grant `admin` to recruiters. **Amended by
[ADR-0044](Work-Project-ADR-0044-No-User-Accounts-Admin-Pre-Shared-Credential.md)**
(2026-09-11): the admin-Fernando-only *principle* carries forward
unchanged, but the mechanism changes from a Cognito RBAC role to a single
pre-shared credential (there are no user accounts to have roles at all).
The `reviewer`/`demo` role for recruiters below is **cut, not deferred**
— see ADR-0044.

## Context

ADR-0021 proposed possibly granting the app's `admin` role to interested
recruiters for expanded exploration. Codex's review flagged this as a
real least-privilege violation: `admin` is the application's single
highest-privilege role, and granting it to people outside Fernando's
control creates real exposure (visibility into other users' data,
billing, roles) that doesn't actually serve the underlying goal any
better than a scoped role would. Fernando agreed 2026-09-03 after
discussion — not a dire/urgent decision, can be implemented later.

## Decision

- `admin` role stays **Fernando-only**, granted through an out-of-band,
  audited privileged operation (Terraform bootstrap or a break-glass AWS
  CLI/console procedure) — never an in-app self-service endpoint.
- A separate, constrained `reviewer`/`demo` role is added later (not
  urgent, deferred past initial build) for recruiters who want expanded
  access: sanitized fixtures only, larger bounded quotas or feature
  visibility, no access to other users' data, billing, roles, or system
  configuration. Time-bound invitations preferred over persistent
  elevated accounts.

## Consequences

- Updates ADR-0021/the system design notes's RBAC section — two
  tiers (standard/admin) becomes three (standard/reviewer/admin) once the
  reviewer role is built, admin narrowed to Fernando-only immediately.
- No urgency to build the reviewer role before other v1 work — explicitly
  deferrable.

## Full reasoning

See an independent design review §"ADR-0021" and conversation
2026-09-03 confirming this with Fernando directly.
