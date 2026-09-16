---
title: "ADR 0016: Frontend Framework — Next.js"
type: decision
tags: [adr, project, work-project, archibrief]
created: "2026-09-03"
updated: "2026-09-03"
status: accepted
---

# ADR 0016: Frontend Framework — Next.js

**Status:** Accepted (2026-09-03) — **amended by
[[Work-Project-ADR-0042-Minor-Amendments-Batch]]** (2026-09-03): Next.js
choice stands; defaults to static/client rendering with the authenticated
API as the security boundary, adding a server/BFF layer only if a
concrete requirement justifies it.

## Context

Weighed Next.js vs. Astro vs. Remix. This is an interactive, authenticated,
dynamic-data SaaS app (not a content-first site like [[Personal-Website]],
where Astro was a real contender) — Astro is built for shipping minimal
JS on content sites and would fight against this app's shape.

## Decision

**Next.js.** Best technical fit for an authenticated SaaS dashboard with
dynamic data; strongest hiring-signal weight for SWE roles specifically
(deepest ecosystem, most hireable skill set); leverages Fernando's
existing React background.

## Consequences

- Remix remains a documented alternative if a specific flow (e.g. a
  form-heavy submission step) turns out to fit its model better.

## Full reasoning

See `AI-Drafts/Claude/work-project-stack-planning-qa.md` §"Round 2,"
question 1.
