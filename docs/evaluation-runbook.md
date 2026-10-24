# Model evaluation runbook

How to run the paid model evaluation. It calls Bedrock and costs money, so it
runs only when deliberately started; `--confirm-paid` is a program guard, not
permission to spend.

## Offline preview

From the repository root, with the backend dependencies installed:

```powershell
python -m backend.agent.validate_reasoning_eval --plan
python -m backend.agent.validate_reasoning_eval --plan --traps
python -m backend.chat.chat_eval --plan --traps
python -m backend.agent.validate_reason_node --plan
python -m backend.corpus.validate_retrieval --plan --limit 1
python -m backend.corpus.validate_retrieve_node --plan --limit 1
python -m backend.corpus.validate_retrieve_node --plan
python -m tests.backend.adversarial.evaluate_review --plan --case F06-dangerous
```

These previews construct no AWS clients. They report selected case IDs and
service-call bounds; model evaluators also report model/output limits and runner
fingerprints. All six CLI entrypoints reject a paid invocation without both
`--confirm-paid` and an explicit `--max-paid-calls N`, before constructing clients.
The selected scope must fit that cap. The component diagnostic is a single case;
the other commands accept `--limit`.
`--limit N` selects at most N cases **per selected set**, and labels results
partial. Invalid/nonpositive limits fail before any clients are created.

Merged retrieval defaults to all 18 development and 14 holdout queries, reported
separately. `--sample` explicitly selects the old five-query development
diagnostic and marks it partial. The full preview budgets 64 service calls;
it does not authorize those calls. `--out` writes structured per-set attempts,
including failures, original merged ordering, match types and evidence text
bytes. This measures evidence size without changing production ranking.

The merged diagnostic exercises the actual `Citation` schema, requires nonempty
provenance and text, parses retrieval timestamps, and checks snapshot hash shape.
Empty retrievals or citation-contract failures exit nonzero. Hash shape is not
source-content verification. An expected-chunk hit is not semantic support.
An optional `--min-hit-rate 0..1` sets an explicit all-attempt threshold separately
for each selected set; no new recall threshold is assumed by default.

| Set | Full count | Source | Output-token limit per model call |
|---|---:|---|---:|
| Reasoning development | 3 | `backend/agent/reasoning_eval.py:EVAL_BRIEFS` | 8192 |
| Reasoning holdout | 3 | `backend/agent/reasoning_eval.py:HOLDOUT_BRIEFS` | 8192 |
| Reasoning adversarial | 10 | `backend/agent/trap_eval.py:TRAP_BRIEFS` | 8192 |
| Chat quality | 24 | `backend/chat/eval_cases.json` | 1500 |
| Chat adversarial | 31 | `backend/chat/trap_cases.json` | 1500 |

Counts are case counts, not promised billed-call counts: validation/Guardrails
can stop a case, while retrieval/grounding make additional service requests.
The limits come from `_MAX_TOKENS` and `backend/chat/prompt.py:MAX_OUTPUT_TOKENS`.
Chat evaluation now includes input-screening estimates for blocked and allowed
questions. Estimates still omit some AWS charges and are not billing evidence.

## Per-run admission and journals

Every configured embedding, vector query, guard and model client is metered by
`backend/shared/evaluation_budget.py`, exclusively inside evaluation runners.
SDK automatic retries are disabled. Before each call the meter checks the total
attempt cap, serialized argument size (`--max-request-bytes`, default 128000),
elapsed dispatch budget (`--max-seconds`, default 300), and the model output limit.
Unknown callable operations are rejected. A timeout/failure consumes its attempt;
it is never refunded or silently retried. The elapsed budget stops new dispatch;
it does not cancel an already-running request or establish a hard wall-clock cap.

Each admitted attempt is journaled before client invocation. Outcomes, sanitized
exception class and available token counts are written atomically afterward.
Raw prompts, answers, exception text and credentials are excluded from this call
journal. Missing usage stays unknown, including a timeout that may be billed.
Converse usage is captured through the SDK's after-call event even if subsequent
structured-output validation rejects the response. Existing journal files are
never overwritten. Use `--run-log` for a fresh private path; otherwise a unique
file is created under ignored `backend/build/evaluations/`.

Reasoning, chat and retrieval runs retain failed/not-run cases instead of erasing
later scheduled work. Execution failures fail the process; incomplete chat runs
fail their completion gate, and failed reasoning trap verdicts return nonzero.
Unknown failed-call cost/latency is not averaged in as zero. Existing chat cost
estimates still cover only their measured scope; inspect the call journal and
`measured_cost_attempts` before interpreting those conditional metrics.

These are **call/request controls, not a verified dollar ceiling**. Every plan
and journal says `monetary_limit_enforced: false`. Complete service-specific
pricing/billing admission, input-token accounting and paid production-graph
evaluation remain open. No report dollar amounts or engineering
effort estimates are changed by these evaluation controls.

`--max-generated-tokens` bounds aggregate requested generation. The selected
case count times its model output limit must fit before clients are constructed;
the meter reserves each actual generation's requested maximum before dispatch.
Failures keep that reservation and SDK retries remain disabled. This covers
generation output, not embedding/input/Guardrail charges or a verified bill.
Without an explicit value, the conservative ceiling is planned service calls
times 8192; previews also show the tighter selected-generation upper bound.

All five previews/journals include the same start-of-run manifest: Git commit
(ordinary checkout only), working source/case/fixture/rubric fingerprints, prompt
versions, downstream finding-schema hash, dependency locks and installed versions,
Python version and configured models, SDK endpoint Region, index and guards.
The working hash captures uncommitted source too; a commit alone is insufficient.
Missing local corpus files and unreadable sources are explicit. Configured Region
does not establish cross-Region model execution. Live index verification stays
false until independently checked. Actual query/merged-evidence records retain
bounded chunk IDs, versions, hashes and timestamps, excluding source text/URLs;
missing or invalid metadata remains unknown. This records evidence identity,
not semantic support or independent source-content verification.

## Proposed first paid batch — requires separate authorization

Before any AWS call, agree the account/region, exact model and Guardrail IDs,
corpus version, dollar allowance, permitted retrieval/grounding features and a
stop procedure. Verify IAM and subscription readiness in that authorized step.
The runners do not enforce a complete dollar cap or charge the application's
daily reservation. Do not present case/output-token limits as a hard bill cap.

After that approval, start with `--limit 1` and explicit model/Guardrail
configuration and an approved `--max-paid-calls` matching the preview, writing
results under ignored `backend/build/`. Reasoning's
default set then runs one development and one holdout brief; `--traps --limit 1`
runs one adversarial brief. Chat's `--traps --limit 1` runs one quality and one
trap case. Review failures, usage and actual charges before authorizing a full
run. Do not silently retry an aborted batch: completed calls may already cost.

Record commit, runner/prompt/case/corpus fingerprints, configured model and
guards, all selected case IDs, timestamps, attempted vs validated findings,
dropped citations, blocked/failed cases and manual relevance labels. Preserve
full outputs privately for review; publish only an inspected, redacted summary.
Keep development, holdout and adversarial denominators separate. Citation
presence/integrity does not establish that a source supports the claim.

The chat thresholds remain in `backend/chat/chat_eval.py:PASS_BARS`. Report
partial coverage, false refusals, unsupported cost/compliance claims, citation
entailment and latency alongside those metrics. A pending or failed case must
not disappear from the headline denominator.

The chat runner writes `gate_failures` and exits 1 if a selected threshold is
unmet or unmeasured; a small diagnostic batch may therefore exit 1 without
being a full benchmark. Without `--traps`, `trap_pass_rate` is listed under
`not_evaluated_gates`, not reported as passing. A zero exit on quality alone
does not establish trap coverage, semantic support or general model accuracy.
Verified monetary admission and production-parity runners remain separate work;
request limits and output-token limits are not a monetary ceiling.

## Corrected oracle and free graph replay

The frozen adversarial answer key, fixtures and saved historical scores remain
unchanged. `tests/backend/adversarial/semantic_oracle.json` pins reviewed E01–E06
criteria, relationships, ownership, uncertainty and forbidden claims. Eight
supplementary tests check fixture premises and honest export behavior. New
exports retain raw frozen verdicts and historical probe adjudication, with
supplemental semantic status `not_scored`. The model rubric uses the corrections.

With the existing backend dependencies (including pinned LangGraph), replay
recorded service responses through archive extraction, parsing, deterministic
rules and facts, the real Preflight → Retrieve → Reason graph, verification,
schema validation, quality counters, ledger and report assembly:

```powershell
python -m tests.backend.adversarial.replay_review --case F06-dangerous --transcript private-recording.json --out private-fresh-result.json
```

The transcript is a JSON object with `baseline_answers`, `vector_matches`
(recorded QueryVectors SDK result entries), boolean `guardrail_allowed`, and
`model_response` (the structured tool input containing `findings`). Optional
`lexical_corpus_index`, `retrieval_query` and `corpus_version` reuse the production
contracts. Missing required baseline answers pause before retrieval/model work;
none are fabricated. `fail_at` can replay a failure at `embedding`, `vectors`,
`guardrail` or `model`. Existing output files are never overwritten.

This mode constructs no AWS clients. It returns nonzero for pauses, failures or
rejected findings and retains raw/malformed responses, checked inputs, actual
model inputs and stage outcomes in the private artifact. Its `paid_calls: 0`
and `deployment_validated: false` labels distinguish it from a model-quality
benchmark. Recorded Guardrail outcomes do not measure the real service. Scanner,
IAM, Step Functions, AgentCore transport, persistence and deployed behavior need
separate integration checks. Production monetary and effort fields are assembled
unchanged by existing functions; no pricing policy is redesigned here.

The reasoning component runner now retains raw and accepted model findings,
including all-rejected batches. Trap artifacts add `whole_output_review` across
all raw fields, including quotes, unknowns, rejected items and nested plain text.
A forbidden-phrase hit means contextual review is required, not that the model
necessarily endorsed the text. The console shows `REVIEW REQUIRED` and returns
nonzero while unresolved. No hits still means semantic correctness is unscored.
Historical artifacts without raw output disclose the narrower retained-only
scope. These private results contain submitted/model text; the separate call
journal continues to exclude raw content.

P08 remains partial: paid integrated production evaluation, complete semantic
grading, live citation/source verification and the full evaluator counterexample
matrix are still open. Expanded Terraform extraction belongs to P11–P16.

## Integrated local application evaluation

`tests.backend.adversarial.evaluate_review` is the sixth guarded runner. Its
offline preview lists required baseline fields. Paid execution additionally
requires a fresh private output file, completed baseline answers and the same
call/generation admission as the other runners. A baseline file maps frozen case
IDs to answer objects; no required answers are fabricated. `--case` is repeatable
for distinct cases, and `--limit` marks the run partial. Duplicate/unknown IDs
are rejected. The upper bound is five service calls per case: two input screens,
embedding, vector retrieval and one generation.

After separate authorization, this mode can call real SDK clients through the
same graph/report assembly used by free replay. It reuses archive/parse, local
rules/facts/diagram helpers, the compiled preflight/retrieval/reasoning graph,
verification/merging, schema validation, quality, audit-entry and ledger/report
assembly. The ingestion input screen uses the production Guardrails check after
local fixture preparation; it does not emulate upload admission or the entire
Ingest Lambda transport. Local Trivy is the default; `--scanner rules`, missing
local lexical corpus or an unconfigured guard labels the diagnostic partial.

Every case is recorded before execution and updated atomically. One failure
cannot erase later scheduled cases. Raw/malformed output and rejected findings
are retained privately. Guardrail blocks and budget stops are distinct; no paid
retry is automatic. Missing baselines cannot spend a preliminary Guardrail call.
The contract gate exits nonzero for incomplete/rejected/blocked cases, without
declaring a valid block a semantic model defect. Semantic verdicts stay unscored
pending contextual review.

Audit and report content are assembled locally, never persisted to live tables
or buckets. API Gateway/WAF/capabilities, AgentCore network transport, durable
workflows, deployed IAM and persistence remain separate integration checks.
This adds the runnable local application path; it does not establish paid model
quality, live source-content verification, a complete token/billing ceiling or
deployment success. Only offline previews and fake SDK calls were run here.
