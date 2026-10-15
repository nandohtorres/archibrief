---
title: "ADR 0047: Landing Page (Option A) and Frontend Quality Gates"
type: decision
tags: [adr, project, work-project, archibrief, frontend, accessibility]
created: "2026-10-15"
updated: "2026-10-15"
status: accepted
---

# ADR 0047: Landing Page (Option A) and Frontend Quality Gates

**Status:** Accepted (2026-10-15). Decided by Fernando.

## Context

Master-list items #7–#9 (Phase 1, "presentable"). The site opened
straight onto an admin-only submission form, and the one public route,
`GET /demo`, wasn't reachable from the UI. Before sharing the site it
needed a real front door, a way into the sample review, and repeatable
checks for phone layout, contrast and Lighthouse scores.

Three landing designs were mocked up as static pages
(`frontend/design/landing-options/` in the archibrief repo):

- **A, editorial:** a large headline ("A second opinion on your AWS
  architecture, *with the receipts.*"), one primary action, sample cards,
  "how a review is built", and "what it can and can't tell you".
- **B, show the product:** the pitch beside a realistic report finding
  with its evidence and citation.
- **C, guided flow:** numbered steps, each showing its output.

## Decision

1. **Option A is the landing page**, built into the app above the
   existing review flow: hero, then samples, then how it works, then
   limits, and finally the "Review your own Terraform" section, which
   holds the existing submission form. B and C stay in the repo; their
   supporting sections (B's finding preview and "what it checks" grid,
   C's step-by-step flow) may be folded in later.
2. **The submission form stays out of the public page until public
   submissions open** (ADR-0046, Phase 3). Visitors see an "opening
   soon" panel that points to the sample instead. The admin key field
   and the real form appear with `?admin` in the URL, or when a key is
   already set for the tab.
   - Why: otherwise a visitor scrolling down hits a form that can only
     fail without the admin key.
3. **Sample cards are honest about what exists.** Only the payments
   sample (`GET /demo`) is marked Ready. The streaming and marketplace
   samples are marked "Coming soon" until they're generated. All
   samples are labeled hypothetical.
4. **"View sample review" loads the real `GET /demo` report.** No admin
   key is sent. The report is labeled "Sample review · hypothetical
   workload", and "Go deeper" on it explains that the sample is
   precomputed instead of starting a paid run.
5. **Frontend quality gates:**
   - Playwright checks at 390px wide, in light and dark: no horizontal
     scroll, and main actions meet the WCAG 2.2 24px target size.
   - A WCAG AA contrast check runs on the rendered page (HTML and SVG
     text) at desktop and phone sizes, with a self-test proving it
     flags known failures.
   - **Lighthouse CI (`@lhci/cli`, dev dependency) via
     `npm run lighthouse`.** It scores the public build and fails below
     95 for accessibility and 90 for best practices; performance and SEO
     only warn. Reports are written to a local folder, never uploaded
     to Google's public report storage.

## Consequences

- First Lighthouse run of the landing page, with phone emulation:
  performance 99, accessibility 100, best practices 100, SEO 100.
- **Adding `@lhci/cli` raises the dev-only `npm audit` count from 14 to
  30.** The new items are in Lighthouse's download and proxy helpers.
  - Accepted because the package only runs on a developer machine or in
    CI against localhost, and never ships in the static site.
  - The production audit stays at 0.
  - The two critical items predate this change (vitest, master-list
    #35).
- The phone/contrast checks start each page already in its theme.
  Switching themes mid-test was flaky in headless Chrome: a few elements
  kept the old theme's colors.
- A deep mobile UI pass is still to do. These checks are the baseline,
  not that pass.
- The sample's citation text still says "Illustrative … span". It is
  replaced when the real samples are generated.

## Alternatives considered

- **Option B or C as the landing page.** Fernando preferred A's
  headline and tone. Parts of B and C stay available.
- **Showing the form to everyone now.** Rejected for the reason in
  decision 2.
- **Running Lighthouse ad hoc via `npx` with no dependency.** It runs
  the same code without a pinned version or committed score floors, so
  results wouldn't be repeatable.
- **axe-core for contrast.** It needs another dependency and doesn't
  handle SVG text well; the diagram is SVG. The rendered-page checker
  covers both, and its self-test guards against it silently passing
  everything.
