---
title: "ADR 0005: Compute — Serverless"
type: decision
tags: [adr, project, work-project, archibrief]
created: "2026-09-02"
updated: "2026-09-03"
status: accepted
---

# ADR 0005: Compute — Serverless

**Status:** Accepted (2026-09-02) — **extended by
[ADR-0028](Work-Project-ADR-0028-Orchestration-Ownership-Boundary.md)**
(2026-09-03): the serverless choice stands; ADR-0028 adds the explicit
ownership boundary between Step Functions, Lambda, and AgentCore/
LangGraph.

## Context

Considered serverless (Lambda + Step Functions + API Gateway) vs.
ECS/Fargate vs. Kubernetes/EKS. Kubernetes was seriously discussed for its
"prestige/seniority signal" value toward Fernando's long-term Solutions
Architect goal.

## Decision

**Serverless** — Lambda + Step Functions + API Gateway. The review
pipeline (discovery → retrieval → rule evaluation → LLM reasoning →
structured output) is a bursty, request-driven, multi-step sequence that
maps naturally onto Step Functions orchestrating Lambda steps — a genuine
realization of the "agent = workflow/controller" mental model, not just a
cost default.

Kubernetes/EKS explicitly rejected as a non-goal: real cost data (EKS
control plane alone ~$0.10/hr / ~$73/mo minimum, before worker nodes, vs.
near-$0 idle serverless cost) plus Fernando's own confirmation he doesn't
want to commit to operating EKS with genuine depth (real autoscaling, a
real node-failure recovery, real upgrades) rather than deploying it
shallowly for signal alone.

## Consequences

- ECS/Fargate remains the documented fallback if a specific pipeline step
  needs longer execution time than Lambda's limits allow.
- Reinforces the "explicitly avoid becoming... a half-operated EKS
  cluster" non-goal already in the Spec.

## Full reasoning

See the project decision log §"Open questions" (compute) for the full Kubernetes
discussion and cost figures.
