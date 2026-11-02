# ADR 0059: Non-Streaming Reasoning and Bounded Model Input

**Status:** Accepted (2026-10-30, PR #53). Supersedes decision 1 of ADR-0058.
Extends ADR-0049 (resource summary) and ADR-0056 (details, risk-ordered cap).

## Context

ADR-0058 made the reasoning call stream, failing after 90 s without a new
chunk. On 2026-10-29 three concurrent reviews failed at 95 s each, every one
a `ReadTimeoutError` inside the stream loop after about 5 s of retrieval and
exactly 90 s of silence. Bedrock holds a forced, strict tool call's output
until it is complete, so a streamed call sends nothing early; the idle limit
was cutting off healthy reviews. The earlier failure (10-28) was a slow
review, not a stalled one: input had grown from about 19k to 46k tokens as
the summary gained facts, and generation slowed with it.

Measured input for a 69-resource review: the resource summary was about 16k
tokens, three quarters of it observation metadata (a hash ID and the
resource name on every fact); retrieved chunks carried full citation
metadata the model never used; rule findings went as full records.

## Decision

1. **One non-streaming `converse` call** that waits up to 400 s for the
   whole answer (240 s for "go deeper"), below what each worker waits for
   the runtime. Never retried. A failed call logs its kind and elapsed time.
2. **Workers check their remaining time.** Below 120 s of Lambda time left
   (90 s for "go deeper"), they skip the model: the review publishes its
   rule findings; "go deeper" fails as `timed_out`. This replaces a 60 s
   floor that could wait longer than the Lambda had left.
3. **Compact model input.** Observations reach the model as facts by
   setting, with absent, unknown and unsupported settings and their reasons
   kept, references by setting, and only inspected coverage domains; full
   bundles stay server-side (`backend/shared/model_observations.py`).
   Chunks go as ID, heading and text; rule findings as category, finding
   and evidence; JSON without spaces. Brief search keeps 6 chunks, topic
   searches 2.
4. **Raised bounds the compact form pays for:** 120 resources (from 80),
   observation budget 160 KB and 640 facts (from 48 KB and 256).
5. **At most 40 rule findings go to the model**: one of each kind first,
   the most severe kinds first, then the most severe repeats, clipped to
   200/500 characters, with `rule_engine_findings_omitted` for the rest.
   The report keeps every rule finding.
6. **Output:** `max_tokens` 12288 (a payments test used 79% of 8192, and a
   cut-off answer loses every model finding); `framework_mapping` derived
   from the cited chunk's corpus metadata; `depth_level` set by mode; at
   most one alternative; length guidance per field; the 12-finding cap
   keeps the most severe and the report says so without marking it partial.
7. **The runtime must import without ingestion-only libraries.** The first
   compact form lived beside code that needs the HCL parser, which the
   runtime package leaves out, and every review's model step crashed at
   import (2026-11-02). A test imports the runtime with those libraries
   blocked.
8. **Size-only logs** for each review: input characters per section,
   resources and passages sent, findings emitted, capped, accepted and
   rejected by kind, and a flag when output passes 80% of `max_tokens`.
   `scripts/analyze_review_logs.py` reports them per review.

## Consequences

- Live hard tests 1-3 completed the model step in 76-94 s; test 3's input
  fell to 24k tokens with all 119 resources shown.
- A submission built to trip 2,602 rules sends about 14k tokens in total
  (CI test), where the uncapped list alone was about 156k.
- Waiting for the whole answer gives no early signal of a stall; the 400 s
  wait bounds it, and the worker still publishes rule findings.
- Rejected: streaming with a longer idle limit (it would only fail later,
  since nothing arrives early) and dropping the strict schema (it is what
  makes the output verifiable).
