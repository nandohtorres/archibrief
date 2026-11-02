# Incident: reviews timing out and falling back to rules only

**Dates:** 2026-10-28 to 2026-11-02. **Impact:** one review failed outright
before the fallback existed; five more published only their rule and
scanner findings. No review failed outright after the fallback shipped. **Fixed in:** PR #52 (fallback), PR #53 (cause, bounds,
import guard). Decisions: [ADR-0058](../adr/0058-streamed-reasoning-findings-cap-and-rules-only-fallback.md),
[ADR-0059](../adr/0059-non-streaming-reasoning-and-bounded-model-input.md).

## Timeline

| When (UTC) | What happened |
|---|---|
| 10-28 19:51 | A 74-resource payments review fails outright: the Bedrock call hits its 240 s read timeout while the model is still writing. The visitor gets nothing, though the rule findings were final. |
| 10-29 | PR #52 deployed: a streamed call (90 s idle, 420 s overall), at most 12 model findings, and a rules-only fallback labeled "the AI analysis did not finish". |
| 10-29 17:56-17:58 | Three hard tests run at once. All three fall back to rules only. |
| 10-29 | Diagnosis (below). PR #53's first commit replaces streaming. |
| 10-29 20:24, 20:31 | Telehealth and payments reviews complete the model step in 90 s and 94 s. |
| 11-02 17:16 | After deploying the compact-input change, two logistics reviews fall back again: the runtime crashes at import. |
| 11-02 17:42 | Fix deployed; the 119-resource logistics review completes in 76 s. |

## Diagnosis

**Logs.** The worker logged `reasoning_unavailable` with
`RuntimeClientError`. The AgentCore runtime's logs, read after the deploy
role was granted access to them, showed `ReadTimeoutError` inside the
stream loop and "Invocation failed" at 95.4, 96.5 and 94.7 s: about 5 s of
retrieval plus exactly 90 s of silence.

**Ruling things out.** A per-call history of `reasoning_call` events showed
healthy reviews taking 20-112 s. The 112 s one had no stall reported,
because before #52 the call didn't stream. Strict-schema compilation (a
first call compiling the tool schema, cached for 24 h) didn't fit: first
calls of the day were not slower, and the failing calls came about 22 h
after the last use.

**Cause.** Bedrock holds a forced, strict tool call's output until the whole
tool input is ready, so a streamed call receives nothing until the end. The
90 s idle limit was therefore a 90 s total limit, and it cut off reviews
that needed 100 s or more. Underneath, input had grown about 2.5 times (19k
to 46k tokens) as the summary gained facts, and generation slowed with it.

**Measuring the input.** For the 69-resource review, the resource summary
was about 16k tokens, three quarters of it observation metadata repeated on
every fact (hash IDs, the resource name, long basis labels); retrieved
chunks carried citation metadata the model never used; rule findings went as
full records. Output averaged about 1,600 characters per finding.

## Fixes

1. One non-streaming call with a 400 s wait; workers check their remaining
   time instead of a 60 s floor.
2. A compact model input: observations by setting with every state kept,
   chunks as ID/heading/text, compact rule findings, fewer chunks per
   search. Test 2's input fell from 45.9k to 32.4k tokens.
3. Bounds the compact form pays for: 120 resources instead of 80, at most
   40 rule findings sent to the model, `max_tokens` 12288. A hostile
   submission built to trip 2,602 rules stays near 14k tokens.
4. Output guidance (length per field, one alternative, framework mapping
   derived from the cited source): about 500 output tokens per finding
   instead of 800.
5. Size-only logs per review and `scripts/analyze_review_logs.py`, which
   names each of the failures above in one line.

## The second failure (11-02)

The compact format first lived next to code that needs the HCL parser.
The runtime package leaves the parser out because only ingestion uses it,
and every test passed because every library is installed locally. In AWS
the runtime crashed at import with `ModuleNotFoundError: No module named
'hcl2'`. The fallback worked as designed. The fix moved the format to a
module with no dependencies, and a new test imports the runtime with the
ingestion-only libraries blocked; it fails with the production error on
the broken commit.

## What changed in how the project works

- A failure of the paid step degrades to a labeled partial report instead
  of an empty one.
- Bounds are measured and tested in CI, including against input built to
  break them, rather than assumed.
- A test now checks what the deployment package actually contains, not
  only what the developer machine has.
- Review health is read from structured logs by a script, not by hand.
