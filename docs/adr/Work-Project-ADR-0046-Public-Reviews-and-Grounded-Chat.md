---
title: "ADR 0046: Public Self-Service Reviews and Grounded Report Chat, Quota-Limited"
type: decision
tags: [adr, project, work-project, archibrief, security, cost]
created: "2026-10-15"
updated: "2026-10-15"
status: accepted
---

# ADR 0046: Public Self-Service Reviews and Grounded Report Chat, Quota-Limited

**Status:** Accepted (2026-10-15, Fernando). Supersedes ADR-0044's
"guest mode fully static" and, for report Q&A only, the spec's "no
back-and-forth in v1." Draft history:
`AI-Drafts/Claude/archibrief-adr-0046-public-reviews-and-chat-draft.md`.

## Context

[ADR-0044](Work-Project-ADR-0044-No-User-Accounts-Admin-Pre-Shared-Credential.md)
kept the public path static: one precomputed report, and only Fernando
could run the paid pipeline. The reason was cost and abuse. A static demo
can't show what the product does; a real run on a visitor's own
Terraform can. Opening it up makes the engineering around cost, abuse,
and injection central rather than optional.

[ADR-0030](Work-Project-ADR-0030-Rate-Limiting-Reframed.md) already called for a
stricter anonymous allowance and salted, minimally retained IP
identifiers; this ADR makes them concrete.

## Decision

### 1. Public, anonymous, no accounts, no email

- Public `POST /reviews` and `POST /reviews/{id}/questions`. No signup,
  no login, **no email collection.**
- The admin key stays, as a quota bypass for Fernando only.
- A review is reachable by its unguessable ID (UUIDv4). The link is the
  access token, and visitors may share it. There is no listing endpoint.

**Email considered and rejected (2026-10-15):** it adds a personal-data
burden (storage, privacy page, deletion, SES sending) for per-person
fairness only, not cost protection. If VPN abuse ever becomes real, the
fallback is a one-time email code with only an HMAC of the address
stored, never the address itself.

### 2. Quotas

| Layer | Limit | Enforced by |
|---|---|---|
| Bot check | Cloudflare Turnstile on submit and first question | Lambda verifies token server-side |
| Burst | ~10 requests / 5 min per IP | AWS WAF rate-based rule |
| Per visitor | **1 review / day** | DynamoDB conditional counter on IP-key, TTL 48h |
| Per review | **5 questions** | Atomic counter on the review record |
| Global | **Daily review + question cap**, set from measured cost to fit the budget | DynamoDB counter checked before any paid call — **the real hard stop** |
| Kill switch | Existing | Checked first |
| Budget | **$50/month, unchanged** until Fernando says otherwise | AWS Budgets alert (delayed backstop) |

- **IP-key:** HMAC-SHA256(secret, IPv4 address or IPv6 /64 prefix). The
  secret lives in Secrets Manager and is rotated monthly. Raw IPs are
  never stored.
- **Accepted weakness:** a VPN resets per-IP limits, and shared NAT can
  lock out legitimate users. The global cap bounds cost regardless.
- **When the cap is hit,** visitors get a plain "Today's free reviews are
  used up — try tomorrow, or view the sample review."

### 3. Cost levers (keep advice tailored, spend less)

1. The deterministic scanner results are free, so they're always shown.
   The model is spent only on synthesis.
2. Bedrock prompt caching on the review context for chat.
3. Answers to the suggested questions are generated in the review call
   itself; only custom questions consume quota.
4. Chat uses a cheaper model if it passes the chat eval; reviews keep the
   current model.
5. An identical archive hash + brief returns the stored review.
6. "Go deeper" consumes a question slot.
7. **Before fixing the global cap,** measure real per-review and
   per-question cost (one instrumented run each, with explicit go-ahead).

### 4. Grounded report chat

- **Context per question:**
  - brief + preflight answers;
  - every finding: evidence, citation + exact quote, confidence inputs,
    risk, recommendation, `alternatives_considered`;
  - the diagram as structured data, once generated;
  - the last ≤4 turns.
- **Optional retrieval:** one retrieval from the WAF corpus for "why not X"
  questions the findings don't cover.
- **Output contract:**
  - every claim cites a finding ID or a retrieved chunk, verified
    server-side;
  - otherwise it says "not determinable from this review";
  - off-topic questions get a fixed refusal.
- **Shape:** stateless Lambda that loads the stored report and returns
  `{answer, citations[], questions_remaining}`.

### 5. Misuse and injection defense — staged, and tested

Every untrusted input passes the same ordered stages before it can
influence model output. Untrusted inputs are the brief, archive contents,
resource names, chat questions, and prior chat turns.

| # | Stage | What it does |
|---|---|---|
| 1 | Normalize | Unicode NFKC, strip zero-width/control/bidi characters, collapse whitespace — defeats hidden-text and homoglyph tricks |
| 2 | Bound | Hard length caps (brief, question ≤500 chars, turns ≤4, archive limits per ADR-0027); identifiers in rule findings truncated and charset-restricted |
| 3 | Scan | Bedrock Guardrails prompt-attack + denied-topics filter on brief and every question; secret-pattern scan on uploaded archives (reject, never echo the match) |
| 4 | Isolate | Untrusted text passed only as clearly-delimited data fields, never concatenated into instructions; system prompt states it is data (ADR-0038) |
| 5 | Constrain output | Forced tool-use JSON schema; server-side citation verification; finding-type restrictions; answers must cite or say "not determinable" |
| 6 | Scope | Chat refuses anything not about this review (no general assistant, no code generation, no secrets, no other users' data) |
| 7 | Observe | Log blocked/refused events (no raw content beyond what's needed); alarm on spikes |

**Testing — each stage has a test, run continuously:**

- `tests/backend/traps/` — deterministic-layer traps (free, every CI run).
- `backend/agent/trap_eval.py` — reasoning-model traps.
- **New chat trap set:**
  - direct injection ("ignore your rules");
  - indirect injection planted in the brief or resource names, then
    triggered by a question;
  - multi-turn escalation;
  - role-play / "developer mode" jailbreaks;
  - encoding tricks (base64, Unicode lookalikes, zero-width);
  - system-prompt extraction;
  - off-topic use as a free LLM;
  - requests for other reviews' data;
  - cost-amplification prompts ("answer in 10,000 words").
- Unit tests for stages 1–2 (normalizer, length caps) on every CI run.
- Paid model and chat trap suites run on a schedule (e.g. weekly, plus
  before each release) with explicit cost limits, never per-PR.

### 6. Data handling

- "Don't upload secrets or customer data" notice before upload.
- Secret scan on ingest.
- **7-day retention** (S3 lifecycle + DynamoDB TTL) for archives,
  reports, and Q&A.
- Nothing used for training.
- A short plain privacy page.

### 7. Unchanged

ADR-0027 archive hardening, ADR-0038 injection boundaries, ADR-0045
direct upload, idempotency, reserved concurrency, and the kill switch.

## Build order

1. **Presentable:** CI green, dev-only UI hidden in production, real
   `GET /demo` sample review, landing page.
2. **Trustworthy reviews:** Trivy-based deterministic core + custom IAM
   rules, fix false positives, until the trap suite passes.
3. **Public submissions** with the quota layers.
4. **Chat** with stages 1–7 and the chat trap set.
5. **README, demo GIF, public repo.**

## Consequences

- Real marginal cost per visitor, bounded by the global cap.
- New public attack surface: the pipeline, chat, and uploads — which is
  why the staged defenses and their tests are part of this decision, not
  follow-ups.
- New work: Turnstile, quota table, WAF rule, chat endpoint, normalizer,
  secret scan, retention lifecycle, privacy page, capacity UX, chat trap
  set.
