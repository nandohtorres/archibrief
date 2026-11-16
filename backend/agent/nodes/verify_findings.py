"""Default-off P3b production adapter around the shared verifier protocol."""

from backend.shared.finding_verification import (
    SYSTEM_PROMPT,
    VERDICT_SCHEMA,
    VERIFIER_VERSION,
    supported_ids,
    verification_input,
    verify_with_dispatch,
)

__all__ = [
    "SYSTEM_PROMPT",
    "VERDICT_SCHEMA",
    "VERIFIER_VERSION",
    "supported_ids",
    "verification_input",
    "verify_findings_node",
]

from backend.shared.model_request_budget import GenerationBudget
from backend.shared.scope_admission import check_paid_scope


def verify_findings_node(state: dict) -> dict:
    if state.get("verification_enabled") is not True or state.get("deep_mode"):
        return state

    def dispatch(**kwargs):
        budget = state.get("generation_budget")
        if (
            not isinstance(budget, GenerationBudget)
            or not budget.verification_enabled
            or budget.dispatched != 1
        ):
            raise ValueError("shared experimental budget required")
        client = state["reasoning_client"]
        check_paid_scope(state, client)
        budget.check_deadline()
        return client.converse_structured(**kwargs)

    return verify_with_dispatch(state, dispatch)
