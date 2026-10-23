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

## P05 — agreed next design

User chose assembly of the original S3 ledger plus stored child findings. The
original ledger will remain immutable. The shared read projection must enforce
review identity, live TTL, parent membership, deduplication and pagination, and
feed API, chat, diagram and budget consistently. Query reads must follow
`LastEvaluatedKey`, including filtered empty pages, as documented in the
[AWS Query API](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_Query.html).

## Validation

- 71 existing browser tests passed after the UI contract change.
- 165 focused backend tests passed after deployment manifest corrections.
- Frontend unit tests, lint and type checking passed before added integration tests.
- Added checks cover a risky fact, a medium rule, unassessed legacy data, independent
  filtering/ranking, both rejection gates, worker-to-S3-to-report/chat propagation,
  deeper replay counters, and HTML warnings for all-rejected output.
- Full backend rerun and the new browser scenario are pending at this checkpoint.
