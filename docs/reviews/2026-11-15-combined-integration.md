# Combined P2 accuracy and Stakeholder Brief candidate

Candidate: `../archibrief-integration`, branch `feat/p2-stakeholder-integration`,
base `e063dfdaa2f20a08e6391becfeba1ea22b7c9ea0`. Local and uncommitted;
no push, deployment, paid generation or live AWS change performed.

## Captures and integration

Immutable captures live in the main checkout's ignored
`backend/build/integration-snapshots/`:

- `main-p2-accuracy-r2-2026-11-15`: 71 changed files, 21 untracked.
- `stakeholder-complete-2026-11-15`: 51 changed files, 17 untracked, three deletions.

Both source worktrees' captured file bytes were rechecked unchanged after integration.
Nine files overlap; seven merged automatically. The two manual resolutions keep
P2's public review scope alongside Stakeholder Brief metadata in `shared/report.py`,
and review coverage alongside brief coverage and price projection in `lib/chat.ts`.
The other overlaps are deeper-review handler, report workspace, analysis quality,
contracts, workflow, Lambda packaging and workflow tests. Source deletions and
new helper modules were preserved. The ignored integration-merge manifest records
the overlap list and resolved conflicts.

Integration-only repairs:

- Explicit `var(--text)` foreground on `.demo-strip` fixes the dark demo's
  inherited foreground and passes the previously failing contrast check.
  This does not implement before-paint theme selection or system-theme defaults.
- DLQ stakeholder wording now describes the inspection allowance and an alternative
  preservation/retry process when source retention plus inspection cannot fit
  within AWS's 14-day limit. It no longer promises an impossible increase.

## Accuracy critique addressed

Missing backup retention has distinct unspecified wording, with tests;
explicit zero and positive values remain distinct. Concern inference recognizes
new and legacy titles. Module findings use compatible generic wording.
Lambda DLQ guards use named targets rather than rejecting unnamed advice because
an unrelated function has no asynchronous trigger. Object Lock guards bind the
creation claim more narrowly, with counterexamples.

The lost T2-08 capacity finding is retained with a labelled safe correction to
its unsafe in-place-shrink action; evidence and citations are unchanged.
Known-output replay rejects nine problematic findings and corrects one, without
the prior development keyword-coverage loss. This is replay, not a fresh accuracy
score or proof that every retained recommendation is safe.

Versions: `rule_engine@2026-11-15b`, `remediation_checks@2026-11-15b`,
`reason_prompt@2026-11-15-facts`. Do not downgrade to the earlier checklist version.

## Validation

- Combined backend: 1,876 passed; nine skipped for unavailable Trivy binary;
  eight known `coverage_gap` cases deselected, matching CI selection.
- Frontend: 134 passed. Typecheck, lint and formatting passed.
- Full browser suite: 82 passed, including dark contrast, using local mocked APIs.
- Tooling: 11 passed. Backend Ruff checks and formatting passed.
- After final DLQ copy change: 32 Stakeholder Brief unit tests passed; formatting
  corrected. Full browser result predates that final copy edit.
- Demo regeneration check, diff whitespace and Terraform formatting passed.
- Packaging dependency checks include both sides' helper modules. Production ZIP
  build/cold-start and hosted CI were not run here.

Ten existing curated corpus chunk files were copied locally with verified hashes
to enable corpus tests. No corpus download, ingestion, embeddings or paid calls.
Main-source backend before integration: 1,848 passed, nine skipped, eight deselected.

## Remaining release work and decisions

P2's real CountTokens/cost validation remains blocked on administrator access;
the existing scoped administrator handoff applies. No permission changes here.
P3b, citation entailment and fresh holdout judgment remain outstanding. Narrow
text guards and known-output replay do not establish a new release accuracy score.

Claude's four additional documents are preserved under the launch notes'
`stakeholder-redesign/claude-handoff-docs-2026-11-15/`. Checklist 1 informed this
integration. Full theme bootstrap (2), setting provenance (3), and chat prompt/input
price prevention (4) remain follow-ups. Setting provenance needs per-setting
AWS/provider semantics; missing does not always mean off. A chat prompt change
needs its own version and evaluation, separate from current accuracy evidence.

Current price handling sanitizes public chat serialization (including cached
answers) and frontend downloads. Dollar-pattern filtering has limits: it does
not cover every currency/spelled-out amount and intentionally preserves some
code-like dollar tokens. Raw stored review/API fields remain available; do not
describe this as deletion of all amounts from storage or every API field.
Unused pricing-code cleanup and the optional narrow-phone arrow fix are deferred.

No source worktree was overwritten. This is a tested integration candidate,
not a completed accuracy release or a deployed application.
