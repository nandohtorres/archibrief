# ADR 0006: LLM Provider — Bedrock-Primary

**Status:** Accepted (2026-09-02) — **amended by
[ADR-0042](0042-minor-amendments-batch.md)** (2026-09-03):
Bedrock-primary choice stands; narrows the "same model weights/outputs"
claim to a defined domain contract, and adds pinning the deployed model
ID with every report.

## Context

Weighed AWS Bedrock (hosted Claude) vs. calling Anthropic/OpenAI APIs
directly.
Bedrock-hosted and Anthropic-direct Claude use identical model
weights/outputs — the real differences are operational (release lag,
fine-tuning availability).

## Decision

**Bedrock as the deployed default**, built behind a thin provider-agnostic
code layer so Anthropic/OpenAI-direct remains usable, not hard-locked out.
Keeps the production path AWS-native (IAM, VPC endpoints, one bill)
while staying architecturally flexible.

## Consequences

- A provider-agnostic LLM integration layer, deployed on Bedrock in
  production.
- Enables ADR-0014 (optional Hugging Face sub-task via the same
  abstraction, through Bedrock Custom Model Import).
