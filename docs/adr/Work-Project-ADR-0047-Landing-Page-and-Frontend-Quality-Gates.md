---
title: "ADR 0047: Landing Page (Option A) and Frontend Quality Gates"
type: decision
tags: [adr, project, work-project, archibrief, frontend, accessibility]
created: "2026-10-15"
updated: "2026-10-15"
status: accepted
---

# ADR 0047: Landing Page (Option A) and Frontend Quality Gates

**Status:** Accepted (2026-10-15). Decided by Fernando. Decision 2 amended the same day (see below).

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
2. **The full submission form is on the public page, but only the
   owner can submit, until public submissions open** (ADR-0046, Phase 3).
   - The admin key field stays in the header until Fernando says to
     remove it.
   - Without a key, pressing submit sends nothing and explains that
     submissions are limited to the site owner, pointing to the sample.
   - A rejected key gets a plain message instead of the error screen.
   - The real lock is server-side: every submit route already requires
     the admin key (ADR-0044). The page only answers visitors plainly.
   - *Amended 2026-10-15:* the first version hid the form and key field
     from the public, behind `?admin`. Fernando preferred the full page
     visible to everyone, with submitting restricted to him.
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
- Phone pass done the same day:
  - The header is compact: brand and theme share one row, and the admin
    key sits below.
  - The report's summary numbers sit two per row.
  - Finding filters wrap instead of being cut off.
  - The diagram says it can be swiped sideways.
  - Inputs are 16px, so iOS doesn't zoom on focus.
  - Phone tests now enforce 24px tap targets and 16px inputs on every
    screen.
  - Checked in Chrome's phone emulation at 390px, not on a physical
    device.
- The sample's citation text still says "Illustrative … span". It is
  replaced when the real samples are generated.

## Amendment (2026-10-15, later): the master landing and the site fonts

**Master landing.** Fernando picked elements from all three options. A
combined mockup, `option-master.html`, was built next to A, B and C,
which stay in the repo. He approved it ("looks good i love this, lets
finalize this layout"), and it's now the app's landing (`c30134d`):

- **From A:** the editorial hero. The headline is now "A second opinion
  on your Terraform, *with the receipts.*"
- **From C:**
  - the button pair: "View sample review" scrolls to the samples, and
    "Review your own Terraform" scrolls to the form;
  - check marks, centered under the buttons;
  - the numbered how-it-works walkthrough, using the payments sample.
    Steps fade in and the line fills as you scroll; this is off for
    reduced motion.
  - the "What it checks" list and the "won't claim" box.
- **From B:** the sample cards with icons.
- **Form placement:** the submission form moved between the walkthrough
  and "What it checks", where the story turns into the product.
- **Copy:** says "Trivy plus our own rules" instead of "16 rule checks".
- **Unchanged:** submitting is still owner-only.
- **Glass variant:** `option-master-glass.html` (see-through cards over
  faint color glows) was tried. Fernando kept the plain master, and the
  glass file stays for reference.
- **Planned next, waiting on Fernando's answers:** a fuller "try it"
  section in that spot, with instant sample, paste or upload, and
  example architectures for non-technical users.

**Fonts were never loading.** The Google Fonts `@import` in
`globals.css` separated families with `&amp;`. That is HTML escaping,
and it's wrong in CSS, so only IBM Plex Mono ever loaded. IBM Plex Sans
and Source Serif 4 had never appeared on the live site.

- The fonts now come from `next/font`, which is built into Next.js, so
  there's no new dependency (`675f025`). It self-hosts the fonts at build
  time, sizes the fallback fonts to match, and makes no runtime request
  to Google.
- Source Serif's optical-size axis was dropped to halve its preloaded
  size.
- A unit test checks that all three families load this way.

**Lighthouse after the change (3 runs):**
- performance 93/99/93;
- accessibility, best practices and SEO 100;
- layout shift 0.029, down from 0.175 when the fonts first loaded.

The earlier 99/100/100/100 was measured while the fonts weren't loading.

## Alternatives considered

- **Option B or C as the landing page.** Fernando preferred A's
  headline and tone. Parts of B and C stay available.
- **Hiding the form from the public until Phase 3** (the first version
  of decision 2). Replaced the same day: the full page with an
  owner-only submit shows visitors what's coming and keeps the admin
  workflow on the same page.
- **Running Lighthouse ad hoc via `npx` with no dependency.** It runs
  the same code without a pinned version or committed score floors, so
  results wouldn't be repeatable.
- **axe-core for contrast.** It needs another dependency and doesn't
  handle SVG text well; the diagram is SVG. The rendered-page checker
  covers both, and its self-test guards against it silently passing
  everything.
