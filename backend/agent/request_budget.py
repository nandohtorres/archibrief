"""Pure request assembly and conservative admission before paid screening."""

import json

from backend.agent.nodes.preflight import preflight_node
from backend.agent.nodes.reason import (
    _FINDING_INPUT_SCHEMA,
    _TOOL_NAME,
    build_system_prompt,
    build_user_content,
)
from backend.shared.model_request_budget import (
    MAX_REQUEST_BYTES,
    MODEL_ID,
    POLICY_VERSION,
    RequestBudgetExceeded,
    count_input_tokens,
    evidence_limit,
    generation_cost_micro_usd,
    request_utf8_bytes,
    structured_request,
)


def generation_request(payload: dict, chunks: list[dict]) -> dict:
    deep = payload.get("mode") == "deeper"
    fields = (
        payload.get("preflight_fields") if deep else preflight_node(payload)["preflight_fields"]
    )
    content = build_user_content(
        payload["workload_brief"],
        payload.get("rule_findings", []),
        chunks,
        fields,
        payload.get("terraform_resources"),
        payload.get("parent_finding") if deep else None,
    )
    return structured_request(
        MODEL_ID,
        build_system_prompt(deep),
        json.dumps(content, separators=(",", ":")),
        4096 if deep else 12288,
        _TOOL_NAME,
        "Emit the synthesized findings for this review.",
        _FINDING_INPUT_SCHEMA,
    )


def prepare_envelope(payload: dict, token_client: object, reservation: int) -> dict:
    query = payload.get("retrieval_query", "")
    if not isinstance(query, str) or len(query.encode("utf-8")) > 32000:
        raise RequestBudgetExceeded("analysis_input_limit_exceeded")
    deep = payload.get("mode") == "deeper"
    fixed = generation_request(payload, [])
    allowance = evidence_limit(deep)
    byte_bound = request_utf8_bytes(fixed) + allowance
    if byte_bound > MAX_REQUEST_BYTES:
        raise RequestBudgetExceeded("analysis_input_limit_exceeded")
    fixed_tokens = count_input_tokens(token_client, fixed)
    # Evidence bytes include JSON escaping. Budget one token per such byte,
    # plus boundary slack. Recount the exact assembled request at generation.
    token_bound = fixed_tokens + allowance + 64
    other = 10000 if deep else 20000
    cost_bound = (
        generation_cost_micro_usd(token_bound, fixed["inferenceConfig"]["maxTokens"]) + other
    )
    if cost_bound > reservation:
        raise RequestBudgetExceeded("analysis_cost_limit_exceeded")
    return {
        "version": POLICY_VERSION,
        "max_request_bytes": MAX_REQUEST_BYTES,
        "max_evidence_bytes": allowance,
        "request_bound_bytes": byte_bound,
        "input_token_bound": token_bound,
        "cost_bound_micro_usd": cost_bound,
    }
