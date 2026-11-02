# ADR 0060: Rules for Transport Encryption, a Single NAT Gateway and Dead-Letter Retention

**Status:** Accepted (2026-10-30, PR #53). Extends ADR-0048 (Trivy and
concern ownership).

## Context

The live payments test (hard test 1, 2026-10-29) left four planted issues to
the model, which spent its 12 findings elsewhere. Each is a plain fact in
the configuration, so a rule finds it every time and frees model findings
for risks that need several resources together.

## Decision

Trivy already had one of them; the other three are ArchiBrief rules.

| Concern | Finding when | Not a finding |
|---|---|---|
| `lb_tls_policy` (Trivy AWS-0047, now trusted) | A load balancer listener's TLS policy allows TLS 1.0 or 1.1 | A TLS 1.2+ or 1.3 policy |
| `rds_force_ssl` | A DB or cluster parameter group explicitly sets `rds.force_ssl` or `require_secure_transport` off | Unset: the default depends on the engine version |
| `nat_single` | Exactly one NAT gateway for two or more subnets | A count that can't be resolved is skipped, not guessed |
| `sqs_dlq_retention` | A standard queue's dead-letter queue keeps messages for less time than the queue, in `redrive_policy` or a standalone redrive resource | FIFO queues, equal or longer retention, unknown values |

Each has a plain-language recipe, and its framework IDs were checked against
the retrieval corpus (SEC09-BP02, REL10-BP01, REL05-BP04). Rule version
`rule_engine@2026-10-30`.

## Consequences

- On the hard tests the three rules fire on payments and on logistics (its
  dead-letter queue is a real issue the answer key missed) and on neither
  telehealth nor the three demos. Trivy's check fired on payments'
  `ELBSecurityPolicy-2016-08` listener and stayed quiet on logistics' TLS
  1.3 policy.
- `nat_single` can't tell whether the subnets span zones; its text says what
  happens if they do.
- Still missed by rules and model on the same test: the WAF bypass through a
  directly reachable load balancer.
