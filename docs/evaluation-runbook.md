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
```

These previews construct no AWS clients. They report selected case IDs and
service-call bounds; model evaluators also report model/output limits and runner
fingerprints. All five CLI entrypoints reject a paid invocation without both
`--confirm-paid` and an explicit `--max-paid-calls N`, before constructing clients.
The selected scope must fit that cap. The component diagnostic is a single case;
the other commands accept `--limit`.
`--limit N` selects at most N cases **per selected set**, and labels results
partial. Invalid/nonpositive limits fail before any clients are created.

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
pricing/billing admission, a total token policy, full version manifests and
production-graph evaluation remain open. No report dollar amounts or engineering
effort estimates are changed by these evaluation controls.

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
