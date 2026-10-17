# Model evaluation handoff

No paid evaluation was run in this continuation. The earlier restriction on
AWS calls remains in force; `--confirm-paid` is a program guard, not permission.

## Offline preview

From the repository root, use the existing Python interpreter:

```powershell
..\archibrief\backend\.venv\Scripts\python.exe -m backend.agent.validate_reasoning_eval --plan
..\archibrief\backend\.venv\Scripts\python.exe -m backend.agent.validate_reasoning_eval --plan --traps
..\archibrief\backend\.venv\Scripts\python.exe -m backend.chat.chat_eval --plan --traps
```

These previews construct no AWS clients. They report selected case IDs, model,
output-token limit, partial-run status and a SHA-256 of the runner. Both runners
reject a paid invocation without `--confirm-paid`, before constructing clients.
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

## Proposed first paid batch — requires separate authorization

Before any AWS call, agree the account/region, exact model and Guardrail IDs,
corpus version, dollar allowance, permitted retrieval/grounding features and a
stop procedure. Verify IAM and subscription readiness in that authorized step.
The runners do not enforce a complete dollar cap or charge the application's
daily reservation. Do not present case/output-token limits as a hard bill cap.

After that approval, start with `--limit 1` and explicit model/Guardrail
configuration, writing results under ignored `backend/build/`. Reasoning's
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
