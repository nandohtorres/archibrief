# ADR 0054: Ask the Regulatory Question Up Front; Reviews Never Pause

**Status:** Accepted (2026-10-27, PR #39; pause path removed 2026-10-28,
PRs #48 and #49). Supersedes the "stop and ask" branch of ADR-0031.

## Context

ADR-0031 let PreflightGate stop a review when a field it needed was
missing. In practice only one field ever paused: regulatory and data
residency requirements. The review waited (a Step Functions
`waitForTaskToken` state, up to seven days) on a clarification screen the
visitor had to come back to. That was a confusing middle state, and it
cost a task-token Lambda, a resume path in the worker, a clarify API route
and its own spending reservation.

## Decision

1. **The submission form asks the question.** "Regulatory or data
   residency requirements" is a required Yes/No; Yes needs at least one of
   GDPR, HIPAA, PCI-DSS, CCPA or Other. `submit_review` refuses a
   submission without it (`SUBMISSION_REQUIRED_FIELDS` in
   `backend/shared/baseline.py`).
2. **PreflightGate never pauses.** `regulatory_data_residency` is
   `CANNOT_INFER`: a review that somehow lacks it records "unknown" and
   runs on. Traffic and availability keep labeled defaults (ADR-0031's
   other two branches stand).
3. **The pause is removed in two stages,** frontend first so the site
   never called a missing route: the clarification screen (#48), then the
   `clarify_review` and `store_clarification_token` Lambdas, the
   `POST /reviews/{id}/clarify` route, the state machine's wait and resume
   states, the worker's resume phase and the boundary's
   `states:SendTaskSuccess`/`SendTaskFailure` (#49).
4. If preflight ever returned `needs_clarification`, the worker fails the
   review (`internal_error`) instead of waiting. Reviews paused before the
   change show `clarification_retired` until they expire.

## Consequences

- No review waits on the visitor. The form is one question longer.
- The regulatory answer reaches the model as an answered requirement, so
  a review can hold the code to it (hard test 3 checks an EU-only
  requirement against cross-region copies).
- Left for later: the agent-side pause branch in the AgentCore runtime
  and the clarification failure codes in `mark_review_failed`. They only
  matter for old paused records, which have expired.
