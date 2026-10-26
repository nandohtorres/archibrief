# Report contract redesign — 2026-10-23

Builds on bounded-fix checkpoint `2ec0dbe`, on separate local branch
`codex/report-contract-redesign`. The bounded branch and checkpoint tag remain
independently reviewable. No push, deployment or paid evaluation has occurred.

## P02 — independent assessments

`ReportFinding.assessment` version 1 separates nullable severity, proposed action
(`needed`, `none`, `unknown`) and source (`rule`, `model`, `reviewer`, `unassessed`).
The raw Finding, evidence type and confidence remain separate. Curated rules use
an explicit concern key in the existing catalog; validated model/reviewer plain
blocks provide their own assessments. There is no keyword scoring, confidence
threshold or inference that a fact is safe. Missing assessment stays unknown.

Live API reports always include an assessment. Legacy presentation keys remain
for old clients, with neutral labels, and no longer drive the current UI or chat.
Dashboard filters/order, guided grouping, diagram badges and HTML use the same
assessment semantics. Action proposals sort first, then severity, followed by
unassessed findings and explicit no-action assessments. Chat uses confidence
only as a tie breaker among equal assessments.

Historical demos stay byte-for-byte unchanged. Their existing structured
stakeholder sidecars supply explicit display assessments; JSON export includes
an `assessment_view` alongside preserved records. Live reports exclude unassessed
findings from priced stakeholder projections so a title-derived legacy recipe
does not contradict the canonical assessment. The price catalog and its severity
judgments still require domain review; source labels do not certify correctness.

## P03 — output quality survives publication

The reasoning node records attempted/accepted/rejected model-item counts before
merging deterministic findings. The graph declares this state channel explicitly.
Runtime returns the counts; worker adds the independent final schema stage;
Finalize persists a small allowlisted envelope in S3. API, chat context, screen,
JSON and HTML preserve it. Rejections at the two gates remain separate, avoiding
denominator confusion and preventing raw rejected text/errors from publication.

Lifecycle status `complete` is unchanged. `analysis_quality.outcome` distinguishes
complete output checks, partial output, rules-only, all-rejected, no-findings and
unknown historical metadata. None claims semantic correctness or coverage.
Deeper results return and retain the same counters for idempotent replay.

The chat prompt version changes to `chat_prompt@2026-10-23`; no model behavior
improvement is claimed without a later paid evaluation. Deployment requires
rebuilding affected Lambda packages and the AgentCore runtime together; mixed
versions publish unknown quality rather than inventing counts.

## P05 — shared durable projection implemented; execution redesign remains

User chose assembly of the original S3 ledger plus stored child findings. The
original ledger stays immutable. The shared read projection enforces
review identity, live TTL, parent membership, Finding validation, deduplication
and bounded pagination. API, chat, diagram and budget consume this projection.
Storage read failures fail the request; invalid/orphaned children are excluded
with a visible count. An older deployment missing the findings-table environment
variable explicitly reports `children_available: false`. Query reads follow
`LastEvaluatedKey`, including filtered empty pages, as documented in the
[AWS Query API](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_Query.html).

Each new deeper batch and a `RESULT#<parent>` completion marker commit together
with a conditional removal of the current claim, using the existing transaction
client. Lost claims cannot publish, and a second read after claiming closes the
read/claim race. Empty and all-rejected runs are durable too: replay does not pay
again. New records keep the original review expiry. Legacy child-only records
remain readable with unknown quality. Parent evidence and alternatives reach
the deeper prompt under bounds, and remain historical claims to reassess, not
trusted instructions. Reason prompt version: `reason_prompt@2026-10-23b`.

The browser refreshes the saved report after deeper analysis; reload and exports
use those saved children. A failed refresh or older API retains the explicit
original-budget fallback. Saved chat answers retain their historical evidence;
new calls receive the current projection. Read roles gain only Query access to
the findings table. Chat packages now include the pinned Finding validator.

The subsequent [asynchronous job implementation](2026-10-23-async-deeper.md)
replaces the short synchronous timeout and completes the remaining P05 source
contract. P06 remediation grouping (now deferred by user instruction), P07–P09 evaluation architecture and budgeting,
and P11–P16 typed facts/five coverage domains are also not implemented here.
Budget totals still sum per finding and disclose overlapping work. No scores,
paid-run results or deployment verification are implied by these source fixes.

## Validation

- 1,108 backend tests passed, 5 skipped, 26 documented coverage gaps deselected.
  Includes the real LangGraph state-channel test with the pinned 1.2.16 package.
- 73 browser tests passed, including independent severity/action filtering and
  deeper result reload/export recovery.
- 82 frontend unit tests passed; lint, type checking and formatting passed.
- Added checks cover a risky fact, a medium rule, unassessed legacy data, independent
  filtering/ranking, both rejection gates, worker-to-S3-to-report/chat propagation,
  deeper replay counters, and HTML warnings for all-rejected output.
- Terraform files parse and pass formatting; no provider initialization, plan,
  deployment or live paid submission was run.
- Local environment: Windows, Python 3.14.3, Node 24.14.0; CI targets Python 3.12.
  Pinned graph dependencies were installed in ignored `backend/build/graph-test-deps`
  for the final suite, without altering global packages.
