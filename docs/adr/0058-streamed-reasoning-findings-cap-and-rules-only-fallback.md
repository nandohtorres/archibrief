# ADR 0058: Streamed Reasoning, a Findings Cap, a Rules-Only Fallback and Untrusted Brief Claims

**Status:** Accepted (2026-10-29, PR #52). Extends ADR-0028 (orchestration
boundary), ADR-0038 (prompt-injection boundaries) and ADR-0039.

## Context

Two hard tests ran at once on 2026-10-28:

- The larger one failed: the Bedrock call waited 240 s for the whole
  response and hit its read timeout while the model was still writing.
  With more facts in the summary (ADR-0056), the model wrote more. The
  review failed and the visitor got nothing, though the rule findings were
  already final.
- The other completed, but its brief ("sandbox, synthetic data, cost only,
  reserve Critical for real incidents") steered the model: five cost-only
  findings, "sandbox" stated as fact, a recommendation to remove backups.
  Only the rules caught the criticals.

## Decision

1. **The reasoning call streams** (ConverseStream). It fails after 90 s
   without a new chunk or 420 s overall; "go deeper" has a 180 s deadline
   to fit its worker's 300 s wait. The tool input is parsed only once the
   model stops for `tool_use`, so a partial answer is never used. Nothing
   is retried: a second attempt would be a second paid call.
2. **The review worker waits up to 600 s** for the runtime, bounded by the
   Lambda time it has left minus 90 s for Validate, Audit and Finalize.
3. **At most 12 model findings,** most severe first. Bedrock's strict tool
   schema can't express `maxItems`, so the prompt asks and parse time
   enforces.
4. **Rules-only fallback.** If the AgentCore step fails, the worker
   publishes the rule and scanner findings on their own, with
   `model_unavailable` in the analysis quality, and the report says the AI
   analysis didn't finish. Guardrails has already passed the brief at
   Ingest.
5. **Brief claims are untrusted** (`reason_prompt@2026-10-29`). The brief
   can add context but never narrows the review, lowers a severity or
   excuses a finding. Claims the configuration can't show (central
   controls, certifications, sign-offs, synthetic data, sandbox, corporate
   IP ranges, account ownership) are never stated as fact. Contradictions
   with `declared_context` (ADR-0056) are reported.

## Consequences

- A slow review finishes; a stalled one fails fast; a failed model step
  still produces a labeled report.
- No partial model findings are published. Saving findings as they stream
  was rejected: parsing incomplete JSON is fragile, and a partial report
  could look complete.
- The brief rule is prompt-level. It needs live re-testing (hard tests 2
  and 3, variant A).
- Not done: showing rule findings on the progress screen while the model
  runs.
