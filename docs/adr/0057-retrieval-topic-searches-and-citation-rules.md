# ADR 0057: Topic Searches From Declared Resource Types, and Stricter Citation Rules

**Status:** Accepted (2026-10-28, PR #51; cost topics 2026-10-29, PR #52).
Extends ADR-0020 and ADR-0036 (retrieval) and ADR-0039 (finding fields).

## Context

Retrieval searched with the workload brief alone. A vague brief ("testyy")
brought back only general Security Pillar design principles, and every
finding cited them. A cost-focused brief brought back one general budgeting
chunk, and every cost finding cited it. Findings also bundled unrelated
problems together and hedged facts the summary stated plainly.

## Decision

1. **Topic searches.** Besides the brief, retrieval runs fixed searches
   picked by which resource types the code declares (`TOPIC_QUERIES` in
   `backend/agent/nodes/retrieve.py`), up to 8 in risk order, 3 results
   each. Up to 2 cost topics (right-sizing, pricing model, retention) are
   searched on top so they never crowd out the risk topics. The search text
   is ArchiBrief's own, never the submitter's. "Go deeper" keeps its
   finding-specific query.
2. **Prompt rules** (`reason_prompt@2026-10-28`): cite the chunk that most
   specifically supports the finding; one issue per finding; connect facts
   across resources when together they make a risk; state listed settings
   and details as observed facts, without hedging.
3. **Call budgets** for paid evaluation rise to 25 service calls per case
   (`MAX_RETRIEVAL_CALLS`), recorded in the evaluation runbook.

## Consequences

- More specific citations at the cost of up to 20 extra embedding and
  vector calls per review (fractions of a cent).
- Citation matching still proves provenance, not support (ADR-0038).
