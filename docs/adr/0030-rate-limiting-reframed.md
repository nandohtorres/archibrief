# ADR 0030: Rate Limiting Reframed as Target Plus Layered Controls

**Status:** Accepted (2026-09-03) — **supersedes** ADR-0011's framing of
AWS-level limits as a guaranteed ceiling

## Context

Verified directly against AWS documentation: API Gateway throttling and
usage-plan quotas are explicitly **best-effort**, not guaranteed
ceilings. AWS Budgets actions can apply IAM/SCP policies or target
specific EC2/RDS instances — there is no native "stop all Bedrock/
serverless spend" action. ADR-0011's implied "hard ceiling" framing
overstated what AWS actually guarantees.

## Decision

Rate limiting/cost control remains a day-one requirement (unchanged from
ADR-0011), implemented as overlapping layers rather than a single
guaranteed cap:

- authenticated per-user counters via conditional DynamoDB writes;
- a stricter anonymous/guest allowance plus API Gateway throttling;
- idempotency keys so retries don't create duplicate reviews;
- Lambda reserved concurrency and bounded Step Functions executions;
- AgentCore/model max-iteration, wall-clock, retrieval, and token limits;
- a fast application kill switch checked before paid work starts;
- budget/anomaly alerts as a delayed operational backstop, not the
  primary control.

IP addresses are a weak anonymous identity and privacy-sensitive — retain
only a salted/rotated representation, minimum useful retention period,
never raw IPs in logs long-term.

## Consequences

- Feeds directly into ADR-0040's budget-ceiling reframing.
- The app-level controls, not AWS's native limits, are now explicitly the
  real enforcement layer.
