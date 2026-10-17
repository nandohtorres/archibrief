# ADR 0014: Hugging Face Capability, No Self-Training

**Status:** Accepted (2026-09-02) — **implementation path superseded by
[ADR-0033](0033-hugging-face-path-corrected.md)** (2026-09-03): the
goal stands, but the proposed Custom Model Import path for
Llama Prompt Guard 2 was factually broken (unsupported architecture).

## Context

The question was whether a purpose-built open model exists for this task,
and whether training/fine-tuning a model would add value. No publicly
usable purpose-built model was found (the closest match, TerraFormer, has
unreleased weights — verified directly). Full from-scratch training
requires GPU infrastructure and ML-engineering depth outside this
project's scope.

## Decision

Add an **optional, narrow sub-task** using an imported open-weight
Hugging Face model (Llama/Mistral/Gemma/DeepSeek) via **Bedrock Custom
Model Import** (e.g. a cheap pre-classification step ahead of the
expensive Claude reasoning call). Claude via Bedrock (ADR-0006) remains
the core reasoning/synthesis engine. **No self-training/fine-tuning** —
deferred, not rejected outright; revisit only as its own research pass
if model training becomes an explicit project goal.

## Consequences

- Real use of a Hugging Face model without training-infrastructure cost.
- Stays inside the same AWS-native architecture (Custom Model Import
  scales to zero when idle, fits ADR-0011's cost controls).
