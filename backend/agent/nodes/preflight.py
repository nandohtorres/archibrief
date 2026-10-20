"""LangGraph node: PreflightGate.

Runs inside the AgentCore Runtime + LangGraph subworkflow (ADR-0028), NOT
as a standalone Lambda — Step Functions owns only the outer durable job.

Implements the per-field three-way missing-data policy (ADR-0031):
cannot-infer -> unknown/not-observable; can-model-conservatively -> named
versioned default, tag dependent findings 'assumption'; required -> pause
via Step Functions task-token callback.

The task-token pause/resume call itself needs a deployed Step Functions
state machine (Work-Project-Deployment-Roadmap.md AWS-account blocker) —
that one AWS call is isolated behind `TaskTokenGateway` below so the
field-policy logic is real and testable without it.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol

DEFAULT_VERSION = "preflight_defaults@2026-09-08"


class FieldPolicy(str, Enum):
    CANNOT_INFER = "cannot-infer"
    CAN_MODEL_CONSERVATIVELY = "can-model-conservatively"
    REQUIRED_FOR_REVIEW = "required-for-review"


class FieldOutcome(str, Enum):
    ANSWERED = "answered"
    ASSUMPTION = "assumption"
    UNKNOWN = "unknown"
    PAUSED = "paused"
    STOPPED = "stopped"


# Per-field policy assignment — implementation detail per System-Design's
# "Open / implementation-level TBDs"; this mapping is the first real pass,
# revisit as scenarios are added.
BASELINE_FIELD_POLICIES: dict[str, FieldPolicy] = {
    "regulatory_data_residency": FieldPolicy.REQUIRED_FOR_REVIEW,
    "expected_traffic_scale": FieldPolicy.CAN_MODEL_CONSERVATIVELY,
    "availability_criticality": FieldPolicy.CAN_MODEL_CONSERVATIVELY,
}

CONSERVATIVE_DEFAULTS: dict[str, str] = {
    "expected_traffic_scale": "low-to-moderate, single-region",
    "availability_criticality": "standard (not mission-critical, no multi-region requirement assumed)",
}

# Human-readable labels for the frontend's BaselineAnswer.label (2026-10-01)
# — finalize.handler reads this to assemble the per-field outcomes it
# writes into the evidence ledger (see assemble_baseline_answers there).
# Kept here, not duplicated in finalize.py, since a field's label is a
# property of the field itself, same ownership as BASELINE_FIELD_POLICIES.
FIELD_LABELS: dict[str, str] = {
    "regulatory_data_residency": "Regulatory and data residency",
    "expected_traffic_scale": "Traffic and scale",
    "availability_criticality": "Availability target",
}


class TaskTokenGateway(Protocol):
    def pause_for_clarification(self, review_id: str, field: str, task_token: str) -> None: ...


class PreflightField:
    def __init__(
        self, name: str, outcome: FieldOutcome, value: str | None, is_assumption: bool
    ) -> None:
        self.name = name
        self.outcome = outcome
        self.value = value
        self.is_assumption = is_assumption


def evaluate_field(
    field_name: str,
    provided_answers: dict[str, str],
) -> PreflightField:
    if field_name in provided_answers:
        return PreflightField(
            field_name, FieldOutcome.ANSWERED, provided_answers[field_name], False
        )

    policy = BASELINE_FIELD_POLICIES.get(field_name)
    if policy is FieldPolicy.CANNOT_INFER:
        return PreflightField(field_name, FieldOutcome.UNKNOWN, None, False)
    if policy is FieldPolicy.CAN_MODEL_CONSERVATIVELY:
        return PreflightField(
            field_name, FieldOutcome.ASSUMPTION, CONSERVATIVE_DEFAULTS[field_name], True
        )
    if policy is FieldPolicy.REQUIRED_FOR_REVIEW:
        return PreflightField(field_name, FieldOutcome.PAUSED, None, False)

    raise ValueError(f"no policy registered for baseline field '{field_name}'")


def evaluate_all_fields(provided_answers: dict[str, str]) -> dict[str, PreflightField]:
    return {name: evaluate_field(name, provided_answers) for name in BASELINE_FIELD_POLICIES}


def preflight_node(state: dict) -> dict:
    provided_answers = state.get("baseline_answers", {})
    evaluated = evaluate_all_fields(provided_answers)

    needs_clarification = [f.name for f in evaluated.values() if f.outcome == FieldOutcome.PAUSED]

    field_state = {
        name: {"outcome": f.outcome.value, "value": f.value, "is_assumption": f.is_assumption}
        for name, f in evaluated.items()
    }

    return {
        **state,
        "preflight_fields": field_state,
        "needs_clarification": needs_clarification,
        "status": "needs_clarification" if needs_clarification else "ready",
        "defaults_version": DEFAULT_VERSION,
    }
