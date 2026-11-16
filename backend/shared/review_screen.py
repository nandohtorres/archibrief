"""Screen free text only after a worker has stored scope and budget admission."""

import os

from backend.shared.admission import AdmissionDenied
from backend.shared.clients import GuardrailsClient
from backend.shared.scope_admission import claim_input_screen, finish_input_screen


def screen_review(payload: dict, guardrails_client: object = None) -> bool:
    context = claim_input_screen(payload)
    guard = guardrails_client
    if guard is None:
        guardrail_id = os.environ.get("GUARDRAIL_ID")
        version = os.environ.get("GUARDRAIL_VERSION")
        if not guardrail_id or not version:
            raise AdmissionDenied("input_screen_unavailable")
        guard = GuardrailsClient(
            guardrail_id=guardrail_id, guardrail_version=version, no_retries=True
        )
    answered = payload.get("baseline_answers") or {
        key: field.get("value")
        for key, field in (payload.get("preflight_fields") or {}).items()
        if isinstance(field, dict) and field.get("outcome") == "answered"
    }
    text = "\n".join([payload["workload_brief"], *[str(v) for v in answered.values() if v]])
    allowed = bool(guard.check(text, source="INPUT"))
    finish_input_screen(context, allowed)
    return allowed
