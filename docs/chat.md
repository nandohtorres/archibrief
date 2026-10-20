# Report chat

Ask questions about one finished review and get answers that cite the
review's own findings, its resource settings, its requirements, or AWS
Well-Architected guidance, or that say plainly it can't tell. Decisions
and their reasons are in ADR-0046 §4–§5 and ADR-0050; the threat model's
trust boundary 6 covers the attack surface.

## How a question is answered

```
POST /reviews/{reviewId}/questions
  1. admin key, or CHAT_PUBLIC_ENABLED (off until public access opens)
  2. body shape (unknown fields → 400), kill switch (fails closed)
  3. review exists and is complete
  4. same client_request_id already answered → stored answer, no cost
  5. suggested question already answered → stored answer, free
  6. normalize + bound the question; chat Guardrail (fails closed)
  7. one DynamoDB transaction: review's slot (typed questions only),
     question record, the day's worst-case $ reservation and count
  8. retrieve 3 WAF chunks; one Converse call (Haiku 4.5, cached review
     block, forced strict tool, 20 s, no retry)
  9. verify every citation; fixed text for refusals; hygiene; canary
 10. store, settle the $ reservation to the estimated real cost, log
```

`GET /reviews/{reviewId}/questions` returns the transcript, the
suggested questions (and which are already answered) and the remaining
count. No model call.

| Code | `error` | Question counted? |
|---|---|---|
| 400 | `invalid_request`, `invalid_question` | No |
| 403 | `chat_not_public` | No |
| 404 | `review_not_found` | No |
| 409 | `review_not_complete`, `request_in_progress` | No |
| 429 | `review_quota_exhausted`, `daily_cap_reached`, `too_many_blocked`, `too_many_failed` | No |
| 502 | `answer_failed` | Refunded (first 3 failures per review) |
| 503 | `chat_paused`, `guardrails_unavailable`; `answer_failed` on Bedrock throttling | No / refunded |
| 504 | `answer_timeout` | Refunded (first 3 failures per review) |

Hardening from the pre-deploy code and security reviews: only answered
turns become history (never a blocked or refused
question); a used-up review or day is turned away before the Guardrails
call; after 6 failed paid calls a review takes no more; the browser
reuses a request's id when retrying it, so a timeout isn't charged twice.

## Code

| Path | What it does |
|---|---|
| `backend/shared/sanitize.py` | Stages 1–2: normalize, reject lookalike and encoded text, cap length |
| `backend/shared/citations.py` | The tolerant quote matcher, shared with the review pipeline |
| `backend/chat/context.py` | The review as the model sees it: aliases, compacted findings, the resource summary |
| `backend/chat/prompt.py` | System prompt, tool schema, turn text, history |
| `backend/chat/verify.py` | Stage 5: citation checks, fixed refusals, hygiene, length cap, canary |
| `backend/chat/answer.py` | Retrieve, one model call, verify, optional grounding score |
| `backend/chat/suggested.py` | Suggested questions from the report, no model |
| `backend/chat/pricing.py` | Cost estimates for the daily cap and the log |
| `backend/chat/observe.py` | The one log line per request (no question or answer text) |
| `backend/lambdas/ask_question`, `list_questions` | The two endpoints |
| `infra/modules/api-gateway/chat.tf` | Lambdas, roles, routes, log groups, optional alarms |
| `frontend/components/report-questions.tsx` | The chat UI; `frontend/lib/chat.ts` has the download builder |

## Settings

Terraform variables on `modules/api-gateway` (environment variables on
the Lambda, so they change without a code deploy):

| Variable | Default | Meaning |
|---|---|---|
| `chat_model_id` | Haiku 4.5 (US profile) | The answering model; must be in `chat_model_ids` |
| `chat_questions_per_review` | 5 | Typed questions per review (suggested ones are free) |
| `chat_daily_budget_micro_usd` | 400000 ($0.40) | Estimated spend per UTC day; the hard stop |
| `chat_daily_max_questions` | 100 | Count backstop per UTC day |
| `chat_blocked_per_review` | 5 | Guardrail-blocked questions before a 429 |
| `chat_grounding_check_enabled` | true | Log grounding scores (detect-only) |
| `chat_public_enabled` | false | Second lock; stays false until public access opens |
| `chat_alarms_enabled` | false | Needs `infra/environments/dev/proposed-chat-iam.md` first |

## Tests

- Free, every run: `tests/backend/shared/test_sanitize.py`,
  `tests/backend/chat/` (context, verification, prompt isolation,
  pricing, the 31-case trap suite stubbed, the eval wiring),
  `tests/backend/lambdas/ask_question` and `list_questions` (moto: every
  status code, limits, replay, refunds, suggestions, logging),
  `tests/frontend/chat.test.ts`, `frontend/e2e/report-chat.spec.ts`.
- Paid, run deliberately and never in CI:
  `python -m backend.chat.chat_eval --confirm-paid [--traps] --model <id>`
  runs 24 quality cases over the demo reviews and the 31 trap cases
  against the real model, scored by fixed rules. The model choice is
  the cheapest that clears the bars in `PASS_BARS`.

## Going live, in order

Paid steps are run deliberately, one at a time.

1. `python scripts/package_lambdas.py`, then `terraform apply` (two new
   Lambdas, two routes, the questions table, two guardrails, Haiku in
   the boundary, Finalize's new parameter, and code updates to the
   Lambdas that share `backend/shared/clients`).
2. One live question on a real review (paid, about a cent) to check the
   path, prompt caching on the second question, and the log line.
3. Optional, free: `python scripts/backfill_resource_summary.py
   <review ids>` (dry run), then `--apply`, so older reviews, the demos
   among them, get the resource summary the chat reads.
4. The chat eval (paid, a few dollars across models), then set the model
   and, from the logged grounding scores, whether to block on grounding.
5. `python scripts/pregenerate_demo_chats.py --confirm-paid` (paid) to
   store the demos' suggested answers in `frontend/public/demos/chats/`.
6. Measure real per-question cost and set the daily cap.
7. Public-access controls (Turnstile, visitor limits), then
   `chat_public_enabled`.
   Before that, require review ids to be random UUIDs server-side: a
   review id is the only key to its conversation, and today only the
   frontend generates UUIDs (the API accepts any id matching its pattern).

## Known limits

- A Lambda killed at its 28 s timeout refunds nothing; a retry with the
  same id after 90 s is admitted and charged again. The model read
  timeout (20 s) makes this rare.
- Citations prove that what's cited exists, not that it supports the
  sentence. The grounding score is logged for the eval; the UI says
  "cited answer".
