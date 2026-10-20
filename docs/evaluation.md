# Evaluation evidence

Measured locally with no AWS calls or paid model runs; test counts reflect the
code after the chat, demo cards and launch accessibility specs landed. CI runs
the same suites on every pull request.

The [browser evaluation](evidence/browser-results.md) records all
Playwright counts, the initial failures, the final axe-only rerun, and automated
accessibility limits. It includes a machine-readable per-case result summary.

## Free test results

| Suite | Result | Source and command |
|---|---|---|
| Backend | 607 passed, 1 skipped | `python -m pytest tests/backend -q --tb=short` |
| Frontend unit | 52 passed in 9 files | `cd frontend; npm test`; tests in `tests/frontend/` |
| Deterministic traps | 60 collected; included in the passing backend run | `python -m pytest tests/backend/traps --collect-only -q -p no:cacheprovider` |
| Stubbed chat trap checks | 26 collected; included in the passing backend run | Same collection command with `tests/backend/chat/test_traps_stubbed.py` |
| Playwright | 57 passed, including the accessibility, keyboard, viewport and resilience specs | `cd frontend; npx playwright test` |

None of these is a model-quality measurement. The local frontend run used
Node v24.14.0, and CI repeats the suites on Node 24.

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
execution is needed. Corpus-dependent skips mean this run did not validate the
gitignored corpus. Keep development and holdout model results separate.

The paid runners are `backend/agent/validate_reasoning_eval.py --traps` and
`backend/chat/chat_eval.py`; inspect their approval requirements before any
future run. A useful future artifact should preserve model/prompt/corpus
versions, all attempted findings/citations, rejected findings, blocked briefs,
and per-case verdicts so survival, coverage and semantic support cannot be
mistaken for one another.
