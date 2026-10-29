# ADR 0052: A Monthly Spend Ceiling and an Automatic Kill Switch

**Status:** Accepted (2026-10-26, PR #33). Extends ADR-0030 (layered rate
limiting) and ADR-0040 (budget as a target, real cost reported).

## Context

The launch limits worked out to about three reviews a day site-wide, since
each review keeps its full $0.40 reservation. A visitor who resubmitted got
a 429. Raising the daily limits safely needed a ceiling that holds across
the whole month.

The AWS budget was the only monthly control, and it could only email. Its
SNS topic policy also didn't admit `budgets.amazonaws.com`, so the emails may
never have been delivered.

## Decision

1. **A global monthly scope in admission** (`backend/shared/admission.py`).
   Every paid path (review, deeper review, chat) reserves estimated spend
   against a UTC-month ceiling in the same DynamoDB transaction as its other
   limits. Once $75 is reserved, paid work is refused until the month rolls
   over. A review that fails before any billed call gives its reservation
   back.
2. **The AWS budget is a backstop that acts.** It rises from $20 to $100.
   At 90% of actual spend, a dedicated `spend-stop` SNS topic invokes a
   small Lambda that turns the SSM kill switch on. That Lambda can only
   `ssm:PutParameter` on that one parameter. The switch stays on until the
   owner turns it off.
3. **Both budget topics admit Budgets and CloudWatch**, scoped to this
   account.
4. **Wider daily limits** inside the ceiling: global $8 and 150 requests,
   visitor $2 and 30, review $1.00 and 10; uploads 40 a day, 6 per visitor
   (`infra/environments/dev/main.tf`).

## Consequences

- The monthly admission ceiling is the real-time limit. Billing data lags
  by hours, so the budget stop can act late; it exists for spend admission
  doesn't see.
- Reservations are estimates, not an AWS billing ceiling (threat model,
  residual risk 3).
- `tests/backend/test_defaults_match_terraform.py` fails if handler
  fallbacks drift from the Terraform defaults.
