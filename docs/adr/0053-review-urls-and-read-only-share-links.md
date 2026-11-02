# ADR 0053: Review URLs, Persistent Access and Read-Only Share Links

**Status:** Accepted (2026-10-26, PRs #35 and #36). Extends ADR-0046
(public anonymous reviews).

## Context

Review capabilities lived in tab `sessionStorage`, so closing the tab lost
the review for good. There was no URL for a review and no way to show one
to someone else. Accounts would fix both but were ruled out (ADR-0044,
ADR-0046).

## Decision

1. **Each review has a URL** (`?review=<id>`). It carries only the ID, so
   it grants nothing on its own. A URL names at most one report.
2. **Capabilities persist for the review's lifetime.** Read and write
   tokens move to `localStorage` until the review expires (seven days),
   falling back to `sessionStorage`. The home page lists up to five recent
   reviews from this browser. Opening one reads the saved report and never
   starts a paid review.
3. **Share link** makes a read-only link:
   `?review=<id>#access=<read key>&expires=<time>`. The read key sits in the
   fragment, which browsers never send to a server, and is stripped from the
   address bar on arrival. The write key never leaves the submitting
   browser, and writes also need the original network identifier.
4. Whoever opens a shared link sees the report read-only: no Go deeper, no
   new chat questions, no Share link.

## Consequences

- Script in the page (an XSS) or anyone using the same browser profile can
  read the tokens for up to seven days (threat model T2).
- A shared link works for whoever has it until the review expires; it can't
  be revoked early.
- The privacy page describes local storage and the fragment.
