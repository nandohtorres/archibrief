# ADR 0050: How the Grounded Report Chat Is Built

**Status:** Accepted (2026-10-15). Implements ADR-0046 §3–§6.

The chat design spec (an internal working document) left twelve open
questions, labeled OQ1–OQ12 below, and proposed changes labeled Δ1–Δ3.
They were settled on the spec's recommended answers, except where noted.
Each one can be reversed; none needs a data migration to undo.

## Context

ADR-0046 accepted a grounded chat about a finished review: five questions
per review, every claim cited, staged injection defenses with tests, and
a global daily cost cap. It left the build details to a spec, and the
spec left twelve questions open.

Two things changed since the spec was written:

- ADR-0049 added a sanitized resource summary for the reasoning model.
  That is the "allowlisted inventory" the spec asked for (its Δ3), so the
  chat reuses it instead of building a second one.
- Public submissions (Phase 3: Turnstile, per-visitor quotas, retention)
  aren't built. Every route except `GET /demo` is still admin-only.

## Decision

### 1. Shape

- **Plain Lambda → Bedrock Converse**, not AgentCore (spec OQ5). One model
  call, no agent loop, a role that can invoke only the chat models, and a
  chat failure can't touch the review runtime.
- `POST /reviews/{reviewId}/questions` (`backend/lambdas/ask_question`)
  and `GET /reviews/{reviewId}/questions` (`backend/lambdas/list_questions`).
  Synchronous: Lambda 28 s, integration 29 s, model read timeout 20 s, no
  SDK retry on the paid call.
- The answering pipeline lives in `backend/chat/` so the Lambda and the
  paid eval run the same code.

### 2. Admin-only until Phase 3 (OQ12)

- Both routes sit behind the admin authorizer, like every other route.
- The handler also refuses non-admin callers unless
  `CHAT_PUBLIC_ENABLED=true`, so removing the authorizer alone can't open
  a paid public endpoint. Opening it is Phase 3's job (Turnstile,
  per-visitor caps), and requires an explicit decision.
- The admin key skips the per-review limit but **not** the kill switch or
  the global daily cap (OQ9).

### 3. What the model sees

- The review: brief, baseline answers, every finding compacted (finding,
  evidence, risk, recommendation, alternatives, confidence, its citation's
  exact quote), under short aliases (`F1`, `C-F1`). The model never sees
  UUIDs, so it can't cite another review's finding.
- The resource summary from ADR-0049, which Finalize now stores in the
  evidence ledger. Reviews finalized before this have none, and the model
  is told so.
- Three retrieved WAF chunks (`R1`–`R3`), always retrieved before the one
  model call (spec Δ2).
- The last four turns of this review, **loaded server-side** (spec Δ1).
  The client sends only the question; an unknown body field is a 400, so
  forged "assistant" turns can't be injected.
- All of it as delimited JSON data, labelled untrusted in the system prompt
  (ADR-0038). Prompt caching marks the system prompt and the review block.

### 4. Output contract and verification

- A forced `answer_question` tool: status (`answered`, `not_determinable`,
  `refused`), refusal reason, paragraphs, citations by alias.
- The server keeps only paragraphs with at least one citation it can
  verify: the finding alias exists; a chunk quote really appears in that
  chunk (the review pipeline's tolerant matcher, now shared in
  `backend/shared/citations.py`); a resource is in the summary; a
  requirement is in the baseline answers. Nothing left → a fixed
  "not determinable" text.
- Refusals use fixed texts; the model's words are discarded.
- URLs and markdown links are stripped, one code block of ≤ 20 lines is
  allowed, answers are capped at 1,800 characters, and a per-deploy canary
  token in the system prompt turns any answer containing it into a refusal
  and an alarm-able log line.
- Bedrock's contextual grounding check runs **detect-only** (OQ8): its
  score is logged, never used to block, until the eval shows a safe
  threshold. AWS says chatbot use isn't a supported case for it.

### 5. Limits and cost

| Limit | Value | Enforced by |
|---|---|---|
| Per review | 5 custom questions | Conditional counter on the review item |
| Blocked per review | 5, then 429 | Counter on the review item (per-visitor in Phase 3) |
| Global per day | $ budget (default $0.40) + question count (default 100) | Usage-counters table, checked in the same transaction, before the paid call |
| Burst | 2 req/s, burst 5 on the POST route | API Gateway route throttling |
| Kill switch | existing | Checked first, fails closed |

- Admission is one DynamoDB transaction: review counter, question record,
  global budget reservation (worst-case cost), global count. After the
  call the reservation is settled to the estimated real cost.
- A failed model call (timeout, truncated or malformed output) refunds the
  review's question slot; the budget reservation is kept as spent, since
  Bedrock may already have billed.
- Reserved concurrency isn't used: this account's Lambda concurrency limit
  is below the 10-unreserved minimum (see `step-functions-lambda`'s
  `lambda_reserved_concurrency`). Route throttling plus the $ cap bound
  cost instead (OQ11).
- Budget split for now: about $0.40/day for chat out of the $50/month
  (OQ10). A later cost-measurement step sets the final caps.

### 6. Suggested questions (OQ1)

- Built deterministically from the report (no model): what to fix first,
  explain the top finding for a stakeholder, how to fix it, what couldn't
  be determined, "why not" the first alternative considered.
- Answered **on first click**, stored, and served free after that. They
  don't use one of the five slots, and they're single-turn, so a stored
  answer never depends on one visitor's history. First-click answers do
  count against the global cap.

### 7. Samples and demos (OQ3, changed)

The spec recommended pregenerated answers plus three live questions per
visitor per day on samples. **Live sample questions are deferred to
Phase 3**, because a per-visitor limit needs Phase 3's visitor key, and a
public paid route without it would only be bounded by the global cap.

- The three demos are real stored reviews, so their suggested answers can
  be generated once through the admin path
  (`scripts/pregenerate_demo_chats.py`, paid, needs explicit approval)
  and shipped as static files next to the demo reports.
- The payments sample (`GET /demo`) has no stored review behind it, so it
  shows a short note instead of a chat.
- The offline fixture flow keeps its canned, clearly labelled preview.

### 8. Model (OQ2)

- `CHAT_MODEL_ID`, default **Claude Haiku 4.5** through the US
  inference profile. IAM allows Haiku 4.5 and Sonnet 4.6, so the eval can
  compare them by changing one variable.
- The paid chat eval (`backend/chat/chat_eval.py`, cases in
  `backend/chat/eval_cases.json`) picks the cheapest model that clears
  every bar. It needs explicit approval, and running it locally needs
  the deploy role to be allowed to invoke Haiku (a proposed IAM statement
  is in `infra/environments/dev/proposed-chat-iam.md`).

### 9. Observability and retention

- One JSON log line per question with status, citation counts, tokens,
  estimated cost, latency, model and prompt version. **No question or
  answer text**; a blocked question logs only a hash.
- Chat log groups keep 7 days.
- Question records expire 7 days after they're asked (DynamoDB TTL, and
  every read checks the time, since TTL deletion is late).
- CloudWatch alarms (canary, cost, blocks, errors) are written but off by
  default (`chat_alarms_enabled`), because the deploy role can't create
  alarms or metric filters yet. Turning them on needs the IAM statement in
  `proposed-chat-iam.md`.

### 10. Download (OQ7)

"Download report" builds one self-contained HTML file in the browser (no
scripts, a print stylesheet so Print → PDF works) with the findings and
the conversation. Every value is escaped; no model text is ever inserted
as HTML. The JSON export gains `chat_transcript`.

## Amendment (2026-10-17, after the first live deploy)

Running it live changed four things:

- **Model (§8): Sonnet 4.6, not Haiku 4.5.** The Haiku 4.5 Marketplace subscription can't be completed for this account, so `CHAT_MODEL_ID` defaults to Sonnet 4.6, which the reviews already use (`b99f50c`). The model call's timeout is now sized after retrieval, up to 24 s, so a slow retrieval can't push the whole call past the Lambda limit.
- **Output cap: 1,500 tokens, not 700.** The first live question failed with `answer_failed`: 700 tokens cut answers off mid-citation. Failed answers now log their failure type (`b36c251`).
- **Budget (§5): $1.00/day, counted as spend.** The daily counter used to store the *remaining* budget, fixed at the first question of the day, so a budget change only took effect the next day. It now stores what was spent (`global#{day}#chat_spent_micro_usd`) and compares it with the current budget (`d3063b2`). Measured cost with Sonnet 4.6: 1.1–4.1 cents per question, about 1.9 cents typical with the review cached; 9–18 s per answer.
- **Alarms (§9): deferred to public launch.** They aren't worth the IAM change while the chat is admin-only; the daily budget and kill switch still bound cost.

Also live: boto3 bundled into `ask_question` for S3 Vectors, `chat_busy` on transaction conflicts, every paid-path call time-bounded (`8299a43`), and clearer suggested-question wording (`c8cb3e6`). The paid chat eval has not been run yet.

## Alternatives considered

- **Chat through AgentCore**: shares the review runtime's broad role and
  its cold-start budget; no agent loop needed. Rejected.
- **Client-sent history**: lets anyone forge assistant turns. Rejected.
- **Raw parsed Terraform in the prompt**: free text and possible secrets.
  The ADR-0049 summary carries the facts without either. Rejected.
- **Suggested answers inside the review call (ADR-0046 §3.3)**: grows the
  review prompt and its time budget, and pays for answers nobody clicks.
  Replaced by first-click generation.
- **Opening chat publicly now**: no visitor limits yet. Deferred.

## Consequences

- New Terraform: two Lambdas, two routes, a review-questions table, two
  guardrails (input screening; grounding check), 7-day log groups,
  optional alarms, Haiku 4.5 in the runtime boundary, and Finalize storing
  the resource summary. `terraform apply` is run manually.
- New paid steps, each needing explicit approval: the first live chat
  test, the chat eval and chat trap suite, and the demo suggested-answer
  pregeneration.
- The threat model's "the model never sees Terraform" now has one more
  reader of the ADR-0049 summary: the chat model.
