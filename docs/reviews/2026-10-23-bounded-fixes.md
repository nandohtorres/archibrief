# Bounded portfolio fixes: review ledger

Baseline: `4fb3ac4` (master after PR #28), 2026-10-23. This follows the master
plan's P00–P20 order, implementing bounded fixes and separating larger designs
at Fernando's explicit direction. It is a review branch, not a deployed release.

## Reconciliation and scope

The earlier audit used `00169cc`. Public cutover and gateway-template fixes
subsequently merged. A read-only live-browser check found public verification
copy, no admin-key field and the GitHub source link. No form was submitted;
deployed permissions, concurrency and paid completion were not re-verified.
Those merged fixes are not reimplemented here. No Terraform resources, model
runs, paid evaluations, deployment settings or public-access flags changed.

Frozen answer keys, fixtures, reports and suggested-answer files are unchanged.
The added semantic errata document is a sidecar, not a new passing score.

## Ordered work and remaining findings

| Plan package / finding IDs | Disposition in this branch | Evidence or next decision |
|---|---|---|
| P00; R01/R02/R04, A15 | Current baseline reconciled; public UI/source link already present | Source `4fb3ac4`; read-only live page inspection; no new deployment proof |
| P01; A01/A02/A12 | HTML/JSON carry demo provenance and every reviewer correction; saved answers are labeled stale and carry cited-finding corrections; versions come from records | Every demo has export regression coverage; original outputs remain intact. Paid answer regeneration remains pending |
| P02; A03 | Bounded mitigation: neutral evidence labels, accurate rule count, explicit non-severity explanation | Historical priority keys/order are retained. Full severity/action/confidence schema and ordering remain a separate design |
| P03; A11/M01/M02 | Missing/invalid type or citation-field shapes no longer abort valid siblings; prompt describes inspected scope and separates advice from observed facts | Focused mixed-batch tests; prompt version bumped; real-model effect not measured |
| P03; M03 | Chat retains bounded dedicated missing-evidence notices with total count | Context regression; global prompt/evidence budgeting remains separate |
| P03; A04 | Deferred design: quality envelope across worker/ledger/API/chat/export | Rejection/partial/all-rejected publication issue remains open; no completeness claim added |
| P04; A05/A06 | Static demo query links, history/reload; tab-scoped live recovery; bounded transient-read retries; returning does not claim cancellation | Browser tests for history, downloads, reload without redispatch and transient retry; capabilities never enter URLs |
| P05; A07 | Original resource summary and settled requirements passed into deeper runtime state | Handler regression; older ledgers use explicit empty-context fallbacks |
| P05; A08/A09 | Bounded mitigation: replay IDs deduplicated; original guided budget/chat/diagram scope disclosed; unsupported child follow-up actions restricted | Canonical child assembly, parent-content expansion and asynchronous timeout design remain pending |
| P06; A10 | Resource-count metric renamed; unpriced-cost prose fixed; benchmarks distinguished from predicted losses; overlapping effort disclosed | No prices or task-grouping arithmetic changed. Remediation-group IDs/deduplicated estimates need a separate design |
| P07; M11 | Six fixture semantic disagreements recorded with current primary sources | Errata sidecar; no frozen verdict changed. Executable supplementary oracle cases remain pending |
| P08; M04 | Component verifier receives the same resource facts used by generation | Full production-parity evaluation, all-attempt accounting and evaluator architecture remain separate work |
| P09; M06 | Existing chat pass bars now affect exit status; missing metrics fail; unrun traps are explicitly unassessed; nearest-rank p95 fixed | Free evaluator self-tests. Monetary admission, complete usage accounting and exception journaling are deferred |
| P10/P17; A18/M05/M07–M10/M12 | No paid baseline or broader quality score produced | Requires reviewed runner/oracle design, exact configuration and an approved run budget |
| P11–P16; C01–C06 | Deferred: typed facts/relations and five coverage domains | Separate bounded design per domain; no new detection coverage claimed |
| P18; A13/A14/A16 | Worker/callback/verification docs corrected; locked quickstart and intentional-gap selection explained; obsolete env scaffolding removed; real HTML/trace CI artifacts configured | Historical CI startup cause is still unknown; no guessed root-cause fix |
| P18/P19; A17, R03/R05–R07 | Source-only changes; live/paid/accessibility-manual/performance/privacy/retention/rollback checks pending | Use current rollout records; do not claim that mocked tests validate deployed IAM or billing limits |
| P20; F01–F04 | Short engineering case study, demo links and this evidence ledger delivered; model-dependent demonstrations deferred | No fabricated before/after results, paired-brief model output, performance/cost figures or ownership claims |

## Larger decisions for the next review

1. **Severity:** add independent nullable severity/action fields and explicit
   legacy semantics; derive rule severity from reviewed concerns, not finding type.
   Decide migration and ranking before modifying shared schemas.
2. **Analysis quality:** define a small versioned envelope with stage-specific
   attempted/accepted/rejected counts and sanitized reasons, then preserve it
   end to end. Decide how all-rejected and rules-only results are presented.
3. **Deeper storage:** compare assembling base S3 plus child DynamoDB records
   at read time with versioned append-only report snapshots. Account for chat,
   graph, budget, IAM, pagination, expiry and concurrent writes before choosing.
   Rewriting the original S3 ledger in place is not a safe shortcut.
4. **Evaluation policy:** agree all-attempt records, production parity,
   retrieval/token bounds and conservative next-call cost admission. The new
   exit checks do not turn existing runners into budget-enforced benchmarks.
5. **Coverage:** review typed observation identities, unknowns and limits first;
   then implement placement, routing, retention, selection and entry paths
   separately with positive/negative/unknown controls.
6. **Effort aggregation:** introduce reviewed remediation-group identities
   rather than guessing overlap from finding titles.

## Validation

Final local checks, 2026-10-23:

| Check | Result |
|---|---|
| Backend, `-m "not coverage_gap"`, no pytest cache | 1,079 passed; 5 skipped; 26 deselected |
| Frontend unit | 78 passed |
| Full Playwright suite, two workers | 71 passed |
| Ruff backend format/check | Passed |
| ESLint, TypeScript, frontend Prettier | Passed |
| Workflow YAML and new documentation links | Parsed/resolved |
| Frozen key/hash and saved demo preservation | Verified; no infrastructure or saved-demo file changes |
| Reasoning/chat `--plan --limit 1` | Passed without chargeable calls |

Local suites use mocked AWS/model integrations; they are not semantic quality
or deployed-security measurements. The full browser run includes axe, keyboard,
viewport, contrast and resilience coverage, not a manual accessibility audit.
Frontend dependencies were reused only after confirming the lockfile matched.

The first backend broad-run attempt used a missing basetemp parent; it was
stopped and rerun with a valid short temporary path. The first browser run
passed 70/71: one old assertion required the previous deeper-status wording.
The replacement asserts actual child findings, original-budget disclosure and
replay deduplication; the final full run passed. The earlier 1,079/5/26 audit
count refers to a different revision and must not be treated as this branch's
unchanged test inventory; public cutover removed tests and this branch added others.

## Claude review checklist

- Confirm the full diff preserves historical data and does not change schemas,
  access policy, infrastructure or prices unintentionally.
- Exercise escaped annotations, all three exports, stale-answer corrections,
  unknown demo IDs, history, refresh, expired capabilities and duplicate reads.
- Check effect cancellation and the stored polling deadline; reload/retry must
  not authorize a new upload, execution or paid call.
- Inspect deeper context propagation and the disclosed remaining storage gap.
- Verify new evaluator exit semantics, including partial diagnostic runs.
- Keep unresolved quality/severity/storage/coverage findings open after merging.
