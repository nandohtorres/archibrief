---
title: "ADR 0021: IAM Model and Application-Level RBAC"
type: decision
tags: [adr, project, work-project, archibrief, security]
created: "2026-09-03"
updated: "2026-09-03"
status: accepted
---

# ADR 0021: IAM Model and Application-Level RBAC

**Status:** Accepted (2026-09-03) — **recruiter-admin proposal superseded
by [[Work-Project-ADR-0037-Admin-Fernando-Only]]** (2026-09-03): the
per-function IAM model stands; `admin` is now Fernando-only with a
separate constrained `reviewer` role for recruiters, added later. **The
application-RBAC portion (layer 2) is superseded by
[[Work-Project-ADR-0044-No-User-Accounts-Admin-Pre-Shared-Credential]]**
(2026-09-11): no user accounts, so no app-level roles at all — the
per-function AWS IAM model (layer 1) is unaffected and stands.

## Context

Two distinct concerns, deliberately kept separate per the existing
"application authorization is not AWS IAM" rule: (1) what AWS resources
each backend Lambda function can touch, and (2) what a logged-in human
user is allowed to do inside the app. Fernando initially proposed an
"elevated IAM role for higher users" — clarified during discussion that
this actually belongs in layer 2, not layer 1.

## Decision

**AWS IAM (backend):** one dedicated least-privilege IAM execution role
per Lambda function, never shared between functions, refined using IAM
Access Analyzer against real CloudTrail usage. Standard current AWS best
practice.

**Application-level RBAC (frontend/app):** at minimum two user roles —
`standard` and `admin`. Admin role is for Fernando's own use post-launch
(full authorized access while recording demo/presentation videos) and
may later be selectively granted to interested recruiters who want to
explore beyond the standard/guest experience — exact grant mechanism
deferred, not yet designed.

## Consequences

- Two separate, real permission-control stories for the portfolio: real
  per-function AWS IAM least-privilege, and real application-level RBAC
  — genuinely different skills, both demonstrated.
- Admin-role grant mechanism (how a recruiter would actually receive
  elevated access) is an open implementation detail, not yet decided.

## Full reasoning

See `AI-Drafts/Claude/work-project-stack-planning-qa.md` §"Round 2,"
question 6.
