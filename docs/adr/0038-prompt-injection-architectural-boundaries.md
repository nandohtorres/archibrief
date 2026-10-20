# ADR 0038: Prompt-Injection Defense — Architectural Boundaries Added

**Status:** Accepted (2026-09-03) — **extends** ADR-0022; layer 1's
implementation corrected per ADR-0033

## Context

A design review noted ADR-0022's five controls are real but each has a
stated limit that shouldn't be overclaimed: structured system/user
separation is labeling, not a security boundary; a classifier is
probabilistic; schema validation checks shape, not truth/safety; caps
constrain impact but don't prevent manipulation. Verified directly:
Bedrock Guardrails' prompt-attack filter does **not** inspect tool
results — only the initial tagged input. OWASP's LLM Top 10 covers more
than prompt injection alone (sensitive-information disclosure, supply
chain, improper output handling, vector/embedding weaknesses, unbounded
consumption).

## Decision

Keep all five original controls (layer 1 now implemented via Bedrock
Guardrails per ADR-0033, not Custom Model Import), and add architectural
controls that don't depend on the model behaving correctly:

- the static, no-execution Terraform ingestion boundary (ADR-0027);
- an allowlisted, versioned RAG corpus with controlled ingestion changes;
- no mutating AWS tools or user credentials granted to the reasoning
  runtime in v1;
- minimum IAM permissions for the reasoning runtime (ties to ADR-0021's
  per-function least privilege);
- deterministic allowlists for retrieval and any future tool calls;
- provenance checks requiring every claim to cite retrieved evidence;
- adversarial regression tests: direct injection, instructions hidden in
  Terraform comments/strings, poisoned retrieved text, output
  manipulation, data exfiltration, cross-user access, unbounded
  consumption.
- Evaluate every trust boundary individually (user briefs, Terraform
  strings/comments, retrieved passages, future tool results) — not just
  the initial prompt, since Guardrails' filter doesn't cover tool
  results.

This is one control set inside the broader OWASP LLM Top 10 threat model
(ADR-0041), not the whole security model by itself.

## Consequences

- The adversarial regression test suite is also real, demonstrable test
  coverage — feeds the already-locked "full automated test coverage"
  requirement.
