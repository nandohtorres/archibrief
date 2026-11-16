# Stakeholder Brief Implementation Notes (2026-11-15)

Implements `side-projects/archibrief-launch/stakeholder-redesign/CLAUDE-IMPLEMENTATION-PROMPT-2026-11-15.md`
and the finishing batch in `CLAUDE-FINISHING-PROMPT-2026-11-15.md`.
Decision record: [ADR-0062](../adr/0062-stakeholder-brief.md).

These are results from this worktree only. They are not integrated
validation: Codex owns combining this with P2 and testing the result.

## Where

- Worktree: `C:\Users\ferna\cursor projects\side-projects\archibrief-stakeholder-brief`
- Branch: `feat/stakeholder-brief`, based on `e063dfd`. Nothing is committed,
  pushed, merged or deployed. The main checkout (P2 and evaluation work) was
  not touched.
- `frontend/node_modules` is a directory junction to the main checkout's
  `node_modules` (untracked). Don't install through it; remove the junction,
  not its target, when the worktree is deleted.
- Screenshots (refreshed after the finishing batch):
  `C:\Users\ferna\AppData\Local\Temp\claude\99eb7ac7c4093561\05e09242-c67e-4844-9876-944668fa616c\scratchpad\shots\`
  (brief-desktop.png, brief-mobile.png, brief-desktop-dark.png,
  brief-reviewer-row.png).

## Complete file list

Git diffs omit untracked files. Capture all of these.

**New (untracked)**

- `backend/shared/money_policy.py`
- `backend/shared/stakeholder/presentation.py`
- `docs/adr/0062-stakeholder-brief.md`
- `docs/reviews/2026-11-15-stakeholder-brief-implementation.md`
- `frontend/components/brief-scene.tsx`
- `frontend/components/stakeholder-brief.tsx`
- `frontend/e2e/stakeholder-brief.spec.ts`
- `frontend/lib/brief-scenes.ts`
- `frontend/lib/money-policy.ts`
- `frontend/lib/public-projection.ts`
- `frontend/lib/stakeholder-brief.ts`
- `tests/backend/shared/stakeholder/test_presentation.py`
- `tests/backend/shared/test_money_policy.py`
- `tests/frontend/fixtures/legacy-stakeholder-v1-breach-pattern.json`
- `tests/frontend/money-policy.test.ts`
- `tests/frontend/stakeholder-brief.test.ts`
- `tests/shared/money-policy-cases.json`

**Deleted (staged with `git rm`)**

- `frontend/components/budget-summary.tsx`
- `frontend/components/guided-report.tsx`
- `tests/frontend/stakeholder.test.ts`

**Modified**

- Backend: `backend/chat/access.py`, `backend/lambdas/deeper_review/handler.py`,
  `backend/shared/report.py`
- Scripts: `scripts/build_demo_stakeholder.py`, `scripts/package_lambdas.py`
- Docs: `docs/adr/0051-stakeholder-costs.md` (status line only),
  `docs/adr/README.md`
- Frontend: `frontend/app/globals.css`, `frontend/components/report-questions.tsx`,
  `frontend/components/report-workspace.tsx`, `frontend/lib/analysis-quality.ts`,
  `frontend/lib/chat.ts`, `frontend/lib/contracts.ts`, `frontend/lib/demos.ts`,
  `frontend/lib/report-review.ts`, `frontend/lib/workflow.ts`
- Demo data: `frontend/public/demos/stakeholder/{breach-pattern,fec-database,medicare-platform}.json`
- e2e: `frontend/e2e/{demo-reviews,launch-accessibility,launch-keyboard,launch-viewports,live-critical-path,mobile-and-contrast}.spec.ts`
- Tests: `tests/backend/lambdas/ask_question/test_handler.py`,
  `tests/backend/lambdas/list_questions/test_handler.py`,
  `tests/backend/shared/stakeholder/test_brief.py`,
  `tests/backend/shared/stakeholder/test_demo_views.py`,
  `tests/backend/shared/test_review_projection.py`,
  `tests/frontend/workflow.test.ts`

## What the brief does

- `frontend/lib/stakeholder-brief.ts`: curated text for all 34 catalog
  concerns (title, analogy, scene, Risk, Work proposed, Helps prevent, Still
  exposed, tier, Bigger if, principle), evidence states, `briefCardFor`,
  `buildBrief`, `briefCoverage`, `protectionJobs`.
- `frontend/lib/brief-scenes.ts`, `frontend/components/brief-scene.tsx`:
  15 two-panel pictures ("In the submitted plans" / "Proposed change"). What
  the plans don't show is drawn dashed with "?".
- `frontend/components/stakeholder-brief.tsx`: intro with counts, original
  review date and "not a new review"; Review coverage aside; legend;
  severity-first `<details>` rows; No action section; a collapsed
  "Different protections do different jobs" strip. The first row opens only
  at 681px and wider; every row opens for printing.
- Backend `brief_meta(finding)` adds `{version: 2, concern, concern_source,
  subject}` to rule findings. It never assigns severity.
- Unchanged: severity, concern IDs, title matching, prompts, model schema,
  retention, rule order, metering, `catalog.py`, `pricing.py`, `brief.py`,
  `assessment.py`.

## Finishing batch 1: wording that matches the evidence

**What the rules can establish.** 17 concerns fire on `not truthy(...)` or a
missing resource or attribute (`backend/lambdas/rule_engine/handler.py`,
Trivy checks in `backend/shared/trivy_checks.py`). That covers a setting that
is left out, set to false, or set from a variable the files don't include,
and the finding doesn't record which. So these cards can't tell missing from
false from unknown, and use conditional wording throughout. Recording the
distinction would need a rule-engine change; that belongs to the accuracy
batch.

**Evidence states** (`evidenceStateFor`, shown on each curated card and in
the HTML export):

| State | Concerns |
|---|---|
| not-shown | s3_public_access, s3_encryption, s3_versioning, sns_encryption, ebs_encryption, rds_encryption, rds_multi_az, rds_deletion_protection, rds_backup_retention, dynamodb_pitr, cloudtrail_log_validation, apigw_access_logging, apigw_throttling, cloudfront_logging, cloudfront_waf, ec2_imdsv2, lambda_concurrency |
| absent (resource not in the code) | cloudtrail_present |
| derived (several settings together, AWS defaults where left out) | placement_single_az, invalid_sqs_mapping, versioned_retention_gap, nat_single, public_lambda_url, sqs_dlq_retention, iam_compute_broad_managed |
| name-match | lambda_secret_env |
| declared (risky value set explicitly) | s3_public_policy, sg_open_ingress, sg_admin_ingress, subnet_public_ip, rds_public, iam_wildcard, iam_trust, rds_force_ssl, lb_tls_policy |

`rds_backup_retention` was added to not-shown (Trivy: "unset or 1").
`cloudtrail_present` moved to its own "absent" state.

**Not-shown cards.** Title, risk, work, analogy and picture now say what the
plans show ("The plans don't show a standby copy of the database…"), make
harm conditional ("If it really runs in one Availability Zone…"), and start
the work with confirming where that matters ("Confirm how the database runs
today. If it has no standby…"). Account-wide defaults the code can't show
are named where they apply (S3 account block, EBS default encryption, IMDSv2
account default, usage plans, AWS Backup, logging set up another way).

**The other 17, overclaims fixed:**

- `iam_wildcard`: not "access to everything". The rule also fires on
  `service:*`. Risk names permissions boundaries and organization rules as
  not reviewed.
- `iam_compute_broad_managed`: not "far more access than it needs". The rule
  writes a different risk when a permissions boundary is set; the card says
  it doesn't evaluate the boundary and points to the technical finding.
- `iam_trust`: the trusted principal may be the same organization, so it no
  longer says "outside account". The work names external ID, MFA or an
  organization check. Its key-list picture was removed: the proposed panel
  ("named rooms") showed a fix the card doesn't propose.
- `s3_public_policy`: an account-wide block can override the policy.
- `sg_open_ingress`, `sg_admin_ingress`: reachability depends on attachment
  and routes, which the rule doesn't follow.
- `lambda_secret_env`: the rule matches names only (`_KEY`, `_SECRET`,
  `_TOKEN`, `_PASSWORD`), not values.
- `sqs_dlq_retention`: says AWS's default is used where a period is left out.
  The analogy was corrected; the old one didn't describe the timing.
- `sns_encryption`: no longer claims messages are "stored readable"; it says
  they aren't protected by a key you control.
- `rds_force_ssl`, `lb_tls_policy`, `placement_single_az`, `subnet_public_ip`:
  softer harm wording ("could", "may").
- Pictures: "latch 2 missing" → "not shown"; "One key list opens everything",
  "No earlier version", "One mistaken switch removes the barn", "unsealed
  cabinet", "loose pages" now show the item as not shown (dashed), with
  conditional captions.

Unassessed and not-observable findings stay in the decision list as
**Needs confirmation** and never go to No action (test added). The first
handoff wrongly said not-observable findings went to No action.

## Finishing batch 2: no cost estimates in any public output

**Shared policy.** `frontend/lib/money-policy.ts` and
`backend/shared/money_policy.py` implement the same rules. Both pass the 18
cases in `tests/shared/money-policy-cases.json`: ranges, decimals, scales,
rates, USD/dollars, legacy per-GB prices, a price inside a code fence, and
Terraform/shell syntax left intact. Modes:

- field (short generated fields): each amount becomes "[amount removed]".
- narrative (chat): a prose sentence or list line that states an amount is
  dropped rather than filled with placeholders. If nothing is left, the text
  is "A cost estimate was removed from this answer."
- code (fences, evidence): code fences are not exempt. A bare `$` plus a
  whole number (`$1`, `awk '{print $1,$2}'`) is kept as a positional
  variable; amounts with separators, decimals, a scale, a rate, a range, US$,
  USD or "dollars" are replaced. `${...}` and `$NAME` never match.
- Exact quotes (chat source quotes, finding `citation.exact_text_span`) are
  never edited. One that states a price is omitted and marked
  `quote_omitted: "monetary-amount"`, keeping its source link and anchor.

**Where it applies**

- Server, every public chat response: `backend/chat/access.py
  transcript_item`. New answers, idempotent replays, stored suggested answers
  copied into a transcript, repeat clicks, and the transcript reader
  (`list_questions`) all go through it. It adds `narrative_policy {version,
  amounts_removed, quotes_omitted}` per turn and `amounts_removed` per
  paragraph. Stored items, TTLs and metering are unchanged (tested).
  `money_policy.py` was added to the ask_question and list_questions
  package lists.
- Chat view (`report-questions.tsx`): the same projection runs on what it
  receives, so older servers and saved answers are covered. It shows a note
  where an amount or a quote was removed.
- HTML export (`chat.ts`): findings use the public record (fields, evidence
  and citation). Answers and citations use the public transcript.
- JSON export (`report-review.ts`): a labelled public copy. Findings use
  `publicRecord`. Plain-block estimate fields (`effort_hours_*`,
  `fix_components`, `harm`) are left out, `budget` is left out, and the
  transcript is public. A `public_text_policy` block gives the policy
  version, a note, the changed fields per finding, and chat removal counts.
  IDs, severity, assessments and citation anchors are kept.
- The model prompt and schema are unchanged. Nothing in the prompt stops the
  model writing a price; that is for the accuracy batch.

## Tier and fallback decisions (unchanged from the first batch)

- Tiers mean setup plus ongoing commitment; `rds_multi_az` stays `$$$ Major`;
  `nat_single` is Needs scoping; backup retention is Light with a "Bigger if"
  note.
- Card kinds:
  - curated: a rule finding with a recorded, v2 or legacy concern.
  - summary: a model or reviewer plain block. Labelled, tier Needs scoping,
    no analogy.
  - technical: everything else.

## Tests (this worktree only)

- Frontend unit (`npm.cmd test`): **130 passed**, 17 files.
- Frontend `typecheck`, `lint`, `format:check`: clean.
- Playwright (`CI=1`): stakeholder-brief, demo-reviews, launch-viewports,
  launch-keyboard, mobile-and-contrast, live-critical-path and
  launch-accessibility. **51 passed, 1 failed.**
- The failure is `launch-accessibility` "axe WCAG A/AA: landing, dark",
  `color-contrast` on `#demo-strip-heading`. The heading "No Terraform? Open a
  finished example" (`frontend/components/demo-cards.tsx`) renders in the
  light theme's text colour `#131c24` on the dark background `#121212`
  (ratio 1.08). This branch doesn't change that component or its CSS, and
  the same check failed on base `e063dfd` when tried earlier. It is not
  fixed or waived here; it needs its own fix.
- Backend (venv, `pytest -m "not coverage_gap"`, as CI runs it):
  **1709 passed, 13 skipped, 8 deselected.** Without the marker,
  adversarial `F04-D-07` (a known coverage_gap case) fails.
- `ruff format --check backend` and `ruff check backend` (CI scope) pass.
  `scripts/build_demo_stakeholder.py --check` returns 0.
- New tests:
  - Backend: shared money cases (18) plus a public-answer test.
  - ask_question: new answer + replay without a price while storage keeps
    it; an old stored suggestion served and re-clicked without a price,
    with its priced quote omitted.
  - list_questions: the transcript reader removes a price and storage is
    unchanged.
  - Frontend: the shared cases; public record and chat projection; JSON and
    HTML exports; evidence-case cards (false, left out, unresolved) for
    `rds_multi_az`; IAM boundary wording; name-only secret matches; Needs
    confirmation kept.

## P2 overlap: files both branches touch

Recompute against the base after capture; this is from this side only.

| File | This branch | P2 (from its progress notes) | Merge |
|---|---|---|---|
| `backend/shared/report.py` | adds `brief`; drops `stakeholder`/`budget` from public findings | adds `review_scope` | Combine both |
| `backend/lambdas/deeper_review/handler.py` | calls `report_findings(findings)` | check | Keep P2 guards; apply the call change |
| `backend/chat/access.py` | public projection in `transcript_item` | check | Keep both |
| `scripts/package_lambdas.py` | adds `stakeholder/presentation.py` (get_review, deeper_review) and `money_policy.py` (ask_question, list_questions) | its own additions | Union |
| `frontend/lib/contracts.ts` | slim stakeholder types, `BriefMeta`, chat policy fields, `review_scope` | `review_scope` | `review_scope` identical; keep the rest |
| `frontend/lib/analysis-quality.ts` | `declarationScopeMessage` | same | Identical; take either |
| `frontend/lib/chat.ts` | brief block, public projection, Review coverage line | Review coverage line | Line identical; keep one |
| `frontend/lib/report-review.ts` | public JSON copy | check | Keep both |
| `frontend/components/report-workspace.tsx` | Stakeholder tab | coverage aside | Keep both |
| `frontend/lib/workflow.ts` | budget helpers removed | check P2 doesn't use them | — |
| `frontend/app/globals.css` | brief/print styles; budget styles removed | check | Combine |

## Remaining limits

- The rules don't record missing vs false vs unresolved, so 17 cards stay
  conditional. A rule-engine field for it is accuracy-batch work.
- The model can still write prices; they are removed on output, not
  prevented. Changing the prompt is accuracy-batch work.
- The money patterns cover dollars only (`$`, US$, USD, dollars). Other
  currencies and spelled-out amounts ("forty dollars") are not caught. In
  code, a bare `$40` is kept, because `$4` and `$1` are usually shell
  positional variables; `$1-$2` in shell would be treated as a range.
- `get_review` still returns `record.plain` estimate fields and raw
  generated text in its API response. They are not displayed, and the
  downloads leave them out. `cost_estimate_tier` (low/medium/high) is still
  in the report and the JSON export. It is a resource-count label, not
  money.
- `pricing.py`, the recipes' cost fields and the model's plain-block cost
  fields are unused by public output. Removal is deferred.
- There are no unit render tests (vitest has no JSX transform). Rendering is
  covered by Playwright only.
- On narrow phones, a row with two tags can wrap the chevron to its own line
  (not fixed; optional polish).
- The landing-page dark contrast failure above.
