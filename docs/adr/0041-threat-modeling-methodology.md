# ADR 0041: Threat-Modeling Methodology — STRIDE Primary, OWASP LLM Top 10 Overlay

**Status:** Accepted (2026-09-03) — resolves the remaining open half of
the threat-modeling and prompt-injection-defense research item

## Context

The threat-modeling and prompt-injection-defense research item was only
partially resolved by ADR-0022/0038 — the prompt-injection defense
architecture was decided, but the broader threat-modeling methodology
(which framework to use, how to document it as a standalone artifact) was
still open. A design review recommended a specific hybrid approach, citing OWASP's own
threat-modeling process documentation and NIST's Generative AI Profile.

## Decision

**Hybrid, one clear primary method:**

1. **Primary artifact: system/data-flow threat model with trust
   boundaries and STRIDE analysis.** Forces explicit treatment of the
   browser, API, archive extraction, static Terraform parser, workflow,
   agent runtime, model, retrieval corpus/index, data stores, CI/CD, and
   administrator — matches OWASP's own documented threat-modeling
   process (data-flow/trust-boundary decomposition + STRIDE).
2. **AI-specific completeness overlay: OWASP Top 10 for LLM/GenAI.** Map
   each applicable category to threats, preventive/detective controls,
   tests, and residual risk — a checklist over the threat model, not the
   model itself.
3. **Optional governance appendix: NIST AI RMF Generative AI Profile.**
   Shows risk ownership, measurement, and lifecycle thinking without
   turning a small project into a compliance program.

The threat-model document contains: scope/non-goals, a data-flow diagram,
assets/data classes, trust boundaries, attacker profiles, threat
register, control mapping, abuse cases, test evidence, residual-risk
decisions, and a change log.

## Consequences

- Closes the threat-modeling research item.
- The resulting threat-model document is published with the code
  (`docs/threat-model.md`).
