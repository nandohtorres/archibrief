# Evaluation evidence

Measured locally with no AWS calls or paid model runs. CI runs the same
suites on every pull request.

The [browser evaluation](evidence/browser-results.md) records all
Playwright counts, the initial failures, the final axe-only rerun, and automated
accessibility limits. It includes a machine-readable per-case result summary, the 2026-10-20
cross-browser run and a Lighthouse audit of the live site (desktop 100 in
all four categories; mobile 93 performance, 100 in the rest).

## Free test results

The local configuration-coverage continuation records a backend regression of
1,209 passed / 5 skipped / 26 coverage-gap cases deselected, followed by focused
relationship/public-scope checks. The separate frozen coverage selection has
18 passing and 8 failing cases. These are local source/contract measurements;
see [coverage reconciliation](terraform-coverage.md) and the
[checkpoint ledger](reviews/2026-10-24-configuration-coverage.md). Historical
tables below are preserved, not presented as a rolling score for the new branch.

The counts below record earlier saved runs, not a rolling measurement of HEAD.
The [bounded-fixes review ledger](reviews/2026-10-23-bounded-fixes.md) records
that branch's later checks and their scope separately. A passing CI selection
does not mean the intentionally excluded coverage-gap cases passed.

| Suite | Result | Command |
|---|---|---|
| Backend | 871 passed | `python -m pytest tests/backend --ignore=tests/backend/adversarial -q --tb=short -p no:cacheprovider` |
| Adversarial suite | 217 passed, 18 failed: the 18 are documented coverage gaps, kept failing on purpose ([FIX_REPORT](../tests/backend/adversarial/FIX_REPORT.md)) | `python -m pytest tests/backend/adversarial -q -p no:cacheprovider` |
| Frontend unit | 73 passed in 12 files | `cd frontend; npm test` (tests in `tests/frontend/`) |
| Playwright | 68 passed, including accessibility, keyboard, viewport, contrast and resilience specs | `cd frontend; npx playwright test` |
| Deterministic traps | 60, included in the backend run | `python -m pytest tests/backend/traps -q -p no:cacheprovider` |
| Stubbed chat trap checks | 26, included in the backend run | `python -m pytest tests/backend/chat/test_traps_stubbed.py -q` |
| Lint and types | Ruff, ESLint, TypeScript and Prettier pass | `ruff check backend scripts`; `npm run lint`; `npm run typecheck` |

Four backend tests need the gitignored ingested corpus and one Trivy unit
test is Linux-only; they skip where those aren't available. Earlier runs are recorded in
[`hardening-checks.json`](evidence/hardening-checks.json),
[`publication-checks.json`](evidence/publication-checks.json) and
[`public-admission-checks.json`](evidence/public-admission-checks.json).

None of these is a model-quality measurement; they test deterministic code
and mocked integrations. CI runs the same suites on Python 3.12 and Node 24.

## Deterministic traps

[`test_rule_engine_traps.py`](../tests/backend/traps/test_rule_engine_traps.py)
parses real fixture Terraform and checks dangerous configurations, safe red
herrings, comment injection, and resource-name injection. Each scenario runs
with custom rules alone and with Trivy plus rules. Test count exceeds fixture
count because some fixtures have multiple expected findings.

The fixture directory contains 17 `t*` dangerous scenarios, 6 `f*` safe
scenarios, and 2 `c*` injection scenarios (source: directory names under
`tests/backend/traps/fixtures/`). Coverage includes IAM policies expressed
through JSON/HCL/data sources, variable defaults, alternate security-group
resources, IPv6, module name collisions, IMDS plus broad compute roles, and
counted Aurora instances. It does not establish recall on arbitrary Terraform.

[ADR-0048](adr/0048-trivy-scanner-in-the-review-pipeline.md)
records the initial 14/14 dangerous misses and 3/4 safe false positives, followed
by 14/14 caught and 0/4 safe false positives after the scanner/rule rebuild.
Those are historical fixture denominators, not today's complete suite.

## Regression cases from an outside review

An outside review in October 2026 found text that claimed more than the code
shows. Each is now a test, and the saved demo reports carry reviewer notes
([demos.md](demos.md), bug 7):

| Overstatement | Fix | Test |
|---|---|---|
| S3 rule: "data at rest is unencrypted" when no encryption is declared, though S3 has encrypted new objects by default since January 2023 | Rule text says the setting isn't declared | `test_s3_encryption_finding_does_not_claim_data_is_unencrypted` |
| CloudTrail rule: "API activity would not be recorded" when this code defines no trail, though one may exist elsewhere and Event history keeps 90 days | Rule text allows for a trail elsewhere and names what's missing | `test_cloudtrail_finding_allows_for_a_trail_managed_elsewhere` |
| Finding page called every citationless finding a not-observable gap, including rule findings with direct configuration evidence | Text depends on the finding type | `citationGap` in `tests/frontend/workflow.test.ts` |

Two hand-written demo explanations were also corrected: the breach chain
(a private S3 route alone doesn't close it) and FEC database sign-in (CloudTrail
doesn't log IAM database authentication). The demo stakeholder files are
rebuilt from them, and `build_demo_stakeholder.py --check` keeps them in step.

These tests check wording, not correctness in general: they don't measure
whether other rules or model findings overstate their evidence.

## Model traps: what was actually measured

The current [`TRAP_BRIEFS`](../backend/agent/trap_eval.py) has 10 briefs;
[`reasoning_eval.py`](../backend/agent/reasoning_eval.py) has 3 development
and 3 holdout briefs (local import/`len` inspection). Briefs test false authority,
compliance bait, contradictory requirements, rationalization, injection, vague
input, and resource-summary contradictions. Scoring combines expected-topic
keywords, forbidden phrases and a minimum finding count. It is not an expert
semantic judgment or a proof against injection.

| Historical record | Reported result | Qualification |
|---|---|---|
| `git show 4937c62` | 5/5 scorable traps passed; 3/8 reviews discarded by citation validation | Offline rescore of the first paid run after fixing quoted/refuted bait scoring. End-to-end scorable coverage was 5/8 (62.5%), not an 8/8 success. |
| `git show d6887af` | Final paid trap09 check passed with full recall | No numeric recall denominator or full current-suite result artifact is committed in that message. |
| `git show a375ab0`; `validate_reasoning_eval.py` | Earlier 3/10 briefs discarded when any citation failed | The harness now drops individual invalid findings and reports them; this is a scoring change, not evidence of a new perfect run. |

No current 10-brief aggregate pass rate can be reproduced from the committed
records inspected here. The chat has 31 trap cases and 24 quality cases
(`backend/chat/trap_cases.json`, `eval_cases.json`, and `docs/chat.md`), but
stubbed verification tests do not establish that a real model passes them.
The chat is deployed and runs on Sonnet 4.6; its paid eval is still pending. Live, it answered 15 demo suggested questions (14 answered, 1
not determinable by design) at 1.1-4.1 cents and 9-18 s each.

## Citation pass rate: define the denominator

The first historical run retained 5/8 briefs after citation validation (62.5%;
`4937c62`). That is **brief-level validation survival**, not a per-citation pass
rate: a single invalid quote could discard a whole brief in that harness.
The committed records do not include all raw attempted citations, so the raw
per-citation validation pass rate and semantic-support pass rate are **unknown**.

The three committed real demo reports contain 21/21 model findings with a
citation and nonempty quote (100% **saved citation presence**, not raw generation
success):

| Saved report | Rule findings | Model findings | Model findings with citation and quote |
|---|---:|---:|---:|
| `breach-pattern.json` | 6 | 6 | 6/6 |
| `medicare-platform.json` | 2 | 7 | 7/7 |
| `fec-database.json` | 6 | 8 | 8/8 |

Source: count each `findings[].record` in
[`frontend/public/demos/reports/`](../frontend/public/demos/reports/), split on
`type == "deterministic-rule-result"`, then check `citation` and
`citation.exact_text_span`. The hand audit of every finding is in
[demos.md](demos.md).

`backend/agent/nodes/reason.py` verifies chunk identity and quote matching;
`backend/shared/citations.py` tolerates documented PDF typography and whitespace
differences while retaining the source span. This establishes provenance, not
entailment. The manual [demo audit](demos.md) identifies a weak citation, a false
cost claim, and incorrect or incomplete model observations. A 100% citation
presence figure must never be marketed as 100% factual accuracy.

## Reproduction boundaries

Run the free suites above. Trivy-backed tests use the offline flags in
`backend/lambdas/scan/handler.py`, including `--skip-check-update`; no Terraform
execution is needed. Corpus-dependent tests skip without the
gitignored corpus. Keep development and holdout model results separate.

The paid runners are `backend/agent/validate_reasoning_eval.py --traps` and
`backend/chat/chat_eval.py`; inspect their approval requirements before any
future run. A useful future artifact should preserve model/prompt/corpus
versions, all attempted findings/citations, rejected findings, blocked briefs,
and per-case verdicts so survival, coverage and semantic support cannot be
mistaken for one another.

Both runners now offer `--plan` without constructing AWS clients and require
`--confirm-paid` for execution. See the [evaluation runbook](evaluation-runbook.md)
for case counts, partial batches and the remaining budget/authorization boundary.
