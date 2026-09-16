---
title: "ADR 0014: Hugging Face Capability, No Self-Training"
type: decision
tags: [adr, project, work-project, archibrief]
created: "2026-09-02"
updated: "2026-09-03"
status: accepted
---

# ADR 0014: Hugging Face Capability, No Self-Training

**Status:** Accepted (2026-09-02) — **implementation path superseded by
[[Work-Project-ADR-0033-Hugging-Face-Path-Corrected]]** (2026-09-03): the
resume-signal goal stands, but the proposed Custom Model Import path for
Llama Prompt Guard 2 was factually broken (unsupported architecture).

## Context

Fernando asked whether a purpose-built open model exists for this task,
and whether training/fine-tuning a model would help him stand out. No
publicly usable purpose-built model was found (the closest match,
TerraFormer, has unreleased weights — verified directly). Full
from-scratch training requires GPU infrastructure and skills belonging to
AI/ML Engineer roles specifically, not Fernando's current near-term
target roles (SWE/Cloud Engineer).

## Decision

Add an **optional, narrow sub-task** using an imported open-weight
Hugging Face model (Llama/Mistral/Gemma/DeepSeek) via **Bedrock Custom
Model Import** (e.g. a cheap pre-classification step ahead of the
expensive Claude reasoning call). Claude via Bedrock (ADR-0006) remains
the core reasoning/synthesis engine. **No self-training/fine-tuning** —
deferred, not rejected outright; revisit only if Fernando later decides
to genuinely add AI/ML Engineer as a target role, as its own research
pass.

## Consequences

- Real "worked with Hugging Face models" resume credit without training
  infrastructure cost or role-signal mismatch.
- Stays inside the same AWS-native architecture (Custom Model Import
  scales to zero when idle, fits ADR-0011's cost controls).

## Full reasoning

See [[Work-Project]] §"W1-W4 stack research findings" (Hugging Face
capability subsection).
