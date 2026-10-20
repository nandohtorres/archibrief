# ADR 0051: The Stakeholder View Prices Fixes From Code, Never the Model

**Status:** Accepted (2026-10-20). Extends ADR-0039 (finding fields) and
ADR-0049 (resource summary).

## Context

The guided report was written for the person who approves the work, but
it only restated each finding's risk and recommendation. That reader's
first questions are money questions: what does fixing this cost, how
long does it take, and what happens if we don't? The only cost signal was
`cost_estimate_tier`, a resource-count heuristic that is explicitly not a
dollar figure.

A model asked for prices would give confident numbers with no source,
and the numbers would drift between runs. A wrong price in front of a
budget holder is worse than none.

## Decision

1. **Every dollar figure comes from a dated price table in code**
   (`backend/shared/stakeholder/pricing.py`: us-east-1, on-demand list
   prices, with each item's AWS pricing page). Sized items (servers,
   standby databases, Aurora replicas) are priced at the instance type
   or class the submitted Terraform declares, read from the ADR-0049
   resource summary.
2. **What can't be priced is shown as unpriced, never guessed.** Costs
   that depend on usage (log volume, table size, old object versions),
   and sizes the table doesn't list, appear as "usage-based" with the
   per-unit rate, and are left out of the totals.
3. **Rule findings use hand-written text.** Each rule carries its
   `concern`. `catalog.py` holds, per concern, a plain title, an everyday
   comparison, what could happen, the fix, what the fix adds, an effort
   range and a harm. Older saved findings are matched to a concern by
   their fixed rule titles. A test runs every rule against fixtures to
   keep the two in step.
4. **Model findings get a `plain` block, and the model only names items.**
   Reason's tool schema adds the same fields. `fix_components` can only
   use price-table item names (Shield Advanced excluded), a quantity of
   at most 4, and a size the Terraform actually declares.
   - `verify_plain` drops the block if any text states a price or
     currency amount. The finding itself is kept, because the block only
     feeds this view.
5. **"Cost of not fixing" cites a source or gives a method.** Data
   breach, slow detection and ransomware recovery cite IBM's Cost of a
   Data Breach 2026 and Sophos's State of Ransomware 2026. Downtime and
   runaway bills have no fair average, so they explain how to estimate
   them; downtime uses the review's own availability target.
6. **Verdicts are mechanical.**
   - Fix today: free and critical or high severity.
   - Quick win: free, medium or low severity.
   - Worth the money: costs money, critical or high severity.
   - When budget allows: everything else.

   The budget summary orders fixes by severity, then cost, and keeps
   optional spending (when budget allows) out of the recommended total.
7. **Built when the report is read, not when it is saved**
   (`backend/shared/report.py`). A price-table update reaches older
   reports. If building the view fails, the report is served without it,
   like the diagram.
8. **The demos stay unedited.** Their saved reports predate the `plain`
   block, so `scripts/demo_plain_language.json` holds hand-written text
   for their model findings, and `scripts/build_demo_stakeholder.py`
   writes `public/demos/stakeholder/`. A test fails when those files fall
   behind the price table or catalog.

## Consequences

- Prices go stale. The table is dated (`PRICES_AS_OF`) and the view says
  so; refreshing it is a code change with a test run, and the demo files
  must be rebuilt.
- Effort ranges are rough guides for one engineer who knows the system,
  not estimates for a given team. The view says so.
- Each review's model output grows by roughly 1–2k tokens, about two
  cents a review at current prices.
- The model can still choose the wrong items for a fix (for example, an
  extra server where none is needed). The prices are right, but the
  recipe can be wrong. Like every model finding, it carries the "written
  by the AI" label, and the technical evidence is one click away.
