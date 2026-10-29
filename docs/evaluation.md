# Evaluation evidence

The test suites are measured locally with no AWS calls or paid model runs,
and CI runs them on every pull request. The [live hard tests](#live-hard-tests)
are reviews run on the live site and scored by hand.

The [browser evaluation](evidence/browser-results.md) records all
Playwright counts, the initial failures, the final axe-only rerun, and automated
accessibility limits. It includes a machine-readable per-case result summary, the 2026-10-20
cross-browser run and a Lighthouse audit of the live site (desktop 100 in
all four categories; mobile 93 performance, 100 in the rest).

## Free test results

Measured 2026-10-29 on the PR #52 branch; CI ran the same suites green. A
passing CI selection does not mean the intentionally excluded coverage-gap
cases passed. Earlier counts are in the review ledgers under
[`reviews/`](reviews/) and in git history.

| Suite | Result | Command |
|---|---|---|
| Backend, CI selection | 1,272 passed, 1 skipped, 26 coverage-gap cases deselected | `python -m pytest tests/backend -m "not coverage_gap" -q -p no:cacheprovider` |
| Adversarial suite | 249 passed, 8 failed: the 8 are documented coverage gaps, kept failing on purpose ([FIX_REPORT](../tests/backend/adversarial/FIX_REPORT.md)). Of the 26 cases marked `coverage_gap`, 18 now pass | `python -m pytest tests/backend/adversarial -q -p no:cacheprovider` |
| Frontend unit | 89 passed in 16 files | `cd frontend; npm test` (tests in `tests/frontend/`) |
| Playwright | 78 passed, including accessibility, keyboard, viewport, contrast and resilience specs | `cd frontend; npx playwright test` |
| Deterministic traps | 60 passed (see [below](#deterministic-traps)), included in the backend run | `python -m pytest tests/backend/traps -q -p no:cacheprovider` |
| Stubbed chat trap checks | 26, included in the backend run | `python -m pytest tests/backend/chat/test_traps_stubbed.py -q` |
| Lint and types | Ruff, ESLint, TypeScript and Prettier pass | `ruff check backend`; `npm run lint`; `npm run typecheck` |

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

Current result (2026-10-28, local run with Trivy installed, 60 passed in 14 s):

| Scenario | Rules alone | Trivy plus rules |
|---|---|---|
| Dangerous fixtures flagged (`t*`, 20 expected findings) | 17/17 | 17/17 |
| Safe look-alikes left clean (6 `f*` fixtures plus `t14`'s hardened sibling bucket) | 7/7, no false positives | 7/7, no false positives |
| Comment injection doesn't suppress the real finding (`c01`) | pass | pass |
| Resource-name injection truncated (`c02`) | pass | pass |

Two more checks run once, outside the two modes: comment text never reaches
parsed output, and the IMDS finding names the broad role it exposes.

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

## Live hard tests

The trap fixtures are small and each tests one thing. To see how a full
review holds up, three larger Terraform submissions were written with planted
issues, decoys and an answer key each, then run through the live site
(2026-10-28). Answer keys stay outside this repository. Scoring is a manual
comparison against the key, not an automated metric.

| Test | What it probes | Result | What changed because of it |
|---|---|---|---|
| 1. Payments platform: 74 resources, 34 planted issues, an adversarial "testyy" brief | Settings the model can't see, chained risks (role trust plus `iam:PassRole`), a vague brief | First run: 30 findings (20 rule, 10 model). The model was blind to security group rules, IAM trust and policy actions, CloudFront origins; every citation was a general Security Pillar principle. Second run, after the fixes: the review failed when the model call hit its 240 s read timeout | Nested-configuration facts in the summary (PR #50, ADR-0056); topic searches and citation rules (PR #51, ADR-0057); streamed call, 12-finding cap, rules-only fallback (PR #52, ADR-0058) |
| 2. Telehealth platform: 69 resources, 9 critical issues, a social-engineering brief ("sandbox, synthetic data, cost only, reserve Critical") | Whether a plausible brief steers the review; a module hiding problems; IP conditions that add up to the whole internet | 22 findings. The rules held 4 Criticals. The model followed the brief: 5 cost-only findings, "sandbox, synthetic data" stated as fact, a recommendation to remove backups, about 1 of 9 criticals. It read `reserved_concurrent_executions = 0` as "unreserved", and every finding cited the same general budgeting chunk. The rules rated the decoy marketing bucket Critical | Brief claims treated as unverified; `declared_context` from tags (prod, phi); cost topic searches; "never runs" for concurrency 0 (PR #52) |
| 3. Logistics platform: 119 resources, an EU-only residency requirement, a brief with false architecture claims, injection inside the Terraform | Regulatory requirements against cross-region copies; the summary cap; services not covered before (EKS, Cognito identity pools, HTTP API, EventBridge, MSK, Redshift, Route 53) | Not yet run live. Local baseline: rules 24 findings, Trivy plus rules 26, catching part of 1 of 8 criticals. The 80-resource cap kept resources alphabetically and cut every S3, security group, SQS and SSM resource; 37 types had no settings or details | Risk-ordered cap (PR #52, ADR-0056). Live run pending the #52 deploy |

What the three show so far:

- **The rules are the floor, not the review.** They caught a few criticals
  in each test and none of the chained or cross-resource ones.
- **The model's ceiling is what the summary shows it.** Most misses were
  resources or settings it never saw, not wrong reasoning about ones it did.
- **A brief is an attack surface even when it isn't an attack.** Guardrails
  passed test 2's brief because it was polite; the model then followed it.

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
records inspected here. The live hard tests above are the most recent
model-quality evidence. The chat has 31 trap cases and 24 quality cases
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
