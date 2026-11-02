# ADR 0056: Nested Facts, Declared Context and a Risk-Ordered Cap in the Resource Summary

**Status:** Accepted (2026-10-28, PR #50; extended 2026-10-29, PR #52).
Extends ADR-0049. Replaces its "never included: tags or policy text" rule
with the fixed-vocabulary forms below.

## Context

Live hard tests against planted-issue Terraform (2026-10-28) showed the
model blind to most of what mattered:

- A 74-resource payments platform: security group rules, IAM trust,
  policy actions and CloudFront origins were nested configuration, which
  ADR-0049 left out, so the model guessed or said nothing.
- A telehealth platform submitted with a brief calling it a "throwaway
  sandbox with synthetic data": the code tags everything
  `Environment = prod` and `DataClass = phi`, but the model couldn't see
  tags and repeated the brief as fact.
- A 119-resource logistics platform: the 80-entry cap kept resources in
  alphabetical order by type, so every S3 bucket, security group, SQS
  policy and SSM parameter was cut.

## Decision

1. **`details`: fixed-vocabulary facts from nested configuration**
   (`backend/lambdas/rule_engine/resource_details.py`): security group
   ingress (ports, protocol, source class; dynamic blocks when resolvable),
   role trust (who is trusted, which condition keys, what a GitHub `sub`
   admits), policy statements (allowlisted sensitive actions by name,
   others counted, resource scope), managed policy names on an allowlist,
   CloudFront origins and viewer settings, environment variable counts
   (never names or values), queue dead-letter links and allowlisted DB
   parameters. More scalar settings, including a `has X` form that reports
   only presence.
2. **`declared_context`:** environment and data-classification labels
   from provider `default_tags`, resource `tags` and environment-named
   root variables. Keys and values both come from fixed lists; any other
   value is dropped, so no free text reaches the model through a tag.
   Ingest keeps provider `default_tags` for this.
3. **Placement-only observations** are stated once as
   `default_placement` instead of per resource.
4. **The cap keeps the riskiest resources:** access decisions (policies,
   ACLs, permissions, ingress rules, secrets, SSM parameters, authorizers,
   routes) first, then data stores and anything with listed settings, then
   other services, then wiring. Within a tier each type's first resource
   comes before any type's second. Output stays in (type, name) order.
5. **Derived facts** where the model misread a value: log retention 0 is
   "never expires"; Lambda reserved concurrency 0 is "never runs".

## Consequences

- More facts reach the model without new free text; T14 in the threat
  model covers the larger surface.
- The cap is still 80. A 119-resource submission loses 39 (now the least
  risky). Raising it to 120 costs about 8 KB of input; not yet decided.
- Still invisible: 30+ resource types with no settings or details (EKS,
  Cognito, API Gateway v2, EventBridge, MSK, Redshift, Route 53 and
  others), modules whose inputs reference other resources, launch template
  `user_data`, DynamoDB replicas, `backend` and `output` blocks. See
  [coverage](../terraform-coverage.md).
