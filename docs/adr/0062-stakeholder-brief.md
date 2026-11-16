# ADR 0062: The Stakeholder Brief Explains Work, Not Prices

**Status:** Proposed (2026-11-15). Supersedes the presentation in ADR-0051
(prices, budget summary, cost of not fixing). ADR-0051's price table and
recipes stay in code until the P1 schema work removes them.

## Context

ADR-0051's stakeholder view put dollar figures in front of budget holders.
The figures were sourced, but they were list prices for one region at a
guessed size, and a reader could easily take them as quotes. The view also hid the order of risk behind a budget table, and a
model-written plain block could still state a price.

The audience is a manager, owner or investor without AWS knowledge. They
need to know what is wrong, how serious it is, what the fix involves, what
it prevents and what stays exposed, in that order.

## Decision

1. **Name.** The selector is "Stakeholder" and the heading is
   "Stakeholder Brief".
2. **Layout A: severity-first expandable rows.** Rows are ordered by the
   existing assessment comparison. Each open row shows Risk, Work
   proposed, Helps prevent and Still exposed, then the evidence and a link
   to the technical finding. The first row opens on wide screens only; on
   a phone the list comes first. All rows open for printing.
3. **Analogies only where they hold.** Farm analogies and pictures appear
   only for a deterministic rule finding whose concern is recorded, sent
   by the backend (`brief` v2) or carried by a legacy card, and only for
   the concerns that have one. AI and reviewer findings get a labelled
   plain summary with no analogy. Each curated card states what the
   evidence shows ("not turned on in the submitted files" is not
   "confirmed off").
4. **Commitment tiers instead of prices.** `$ Light`, `$$ Moderate`,
   `$$$ Major` or Needs scoping, with "Bigger if…" notes. A tier means
   setup plus ongoing commitment, so a standby database stays Major. The
   legend says: "Typical overall commitment, not a quote or a verified
   estimate." AI findings are Needs scoping.
5. **No money anywhere in the brief.** The view, chat answers and HTML/
   JSON exports remove dollar amounts and say where one was removed.
   Terraform `${...}` interpolation and `$VARS` are kept. The budget
   object is no longer sent or exported.
6. **Reviewer corrections sit beside the finding** in the view and in
   exports. "Needs confirmation" stays visible.
7. **Scope is disclosed.** The brief states the original review date, that
   it is not a new review, and the review scope (P2's
   `declarationScopeMessage`); with no recorded scope it says not to read
   the brief as complete coverage.
8. **Nothing about the review changes.** Severity, concern IDs, title
   matching, prompts, the model schema, retention, rule order and metering
   are untouched. The backend adds only `brief: {version: 2, concern,
   concern_source, subject}` to rule findings.
9. **Compatibility.** The frontend reads v1 and v2 demo sidecars and old
   saved reports (legacy `stakeholder` cards, inferred concerns). A new
   frontend works against an old backend and the reverse.

## Consequences

- Readers can no longer read a number as a quote, at the cost of no
  budget figure at all. A real estimate needs scoping by someone who can
  see the account.
- The curated text lives in `frontend/lib/stakeholder-brief.ts`, keyed by
  the 34 catalog concerns; a test fails if the catalog gains a concern
  without an entry.
- `pricing.py`, the recipes' cost fields and the model's plain-block cost
  fields become dead weight; removing them is P1 follow-up work.
- The chat model can still write a price; the prompt is unchanged. The
  server removes it from every public chat response (`transcript_item`),
  and the frontend applies the same rules (`money-policy.ts`, shared test
  cases with `backend/shared/money_policy.py`) to old saved answers,
  the view and both downloads. Stored answers are not changed.
