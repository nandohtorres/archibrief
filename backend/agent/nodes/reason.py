"""LangGraph node: Reason.

Runs inside the AgentCore Runtime + LangGraph subworkflow (ADR-0028), NOT
as a standalone Lambda.

Synthesizes RuleEngine output + retrieved evidence into typed `Finding`
objects via Bedrock Claude. Lightweight-first-pass prose by default
(ADR-0023), but every required field is still populated per ADR-0039.
Persists model ID, prompt version, corpus version, and retrieved chunk
IDs as a snapshot (ADR-0039), so a later "go deeper" is a versioned
child, not a disconnected re-run.

Prompt construction uses ADR-0022's structured system/user-content
separation — the workload brief and retrieved evidence are passed as
distinct, clearly-delimited fields, never concatenated into one string
with instructions.

Note on Classify (ADR-0033): no separate Classify node. Guardrails runs
inline at Ingest and again here before calling the model.
"""

from __future__ import annotations

import json
import uuid

from backend.shared.clients import BedrockReasoningClient, GuardrailsClient
from backend.shared.models.finding import (
    AlternativeConsidered,
    ConfidenceInputs,
    Finding,
    FindingCategory,
    FindingType,
)

PROMPT_VERSION = "reason_prompt@2026-09-08"

SYSTEM_PROMPT = """You are ArchiBrief's evidence-grounded reasoning stage.
You synthesize deterministic rule results and retrieved AWS Well-Architected
Framework passages into findings. You must:
- Never state a claim without a citation to the provided retrieved evidence.
- Never label a design "compliant" — describe framework alignment, not
  certification.
- Populate every field in the required JSON schema, even in lightweight mode.
- Tag any finding that depends on an assumed default as type "assumption".
Respond with a JSON array of finding objects matching the schema given in
the user content. Do not include any text outside the JSON array."""


class GuardrailBlocked(Exception):
    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(f"Guardrails blocked content at stage: {stage}")


def build_user_content(
    workload_brief: str,
    rule_findings: list[dict],
    retrieved_chunks: list[dict],
) -> str:
    return json.dumps(
        {
            "workload_brief": workload_brief,
            "rule_engine_findings": rule_findings,
            "retrieved_evidence": retrieved_chunks,
            "required_finding_schema_fields": [
                "category",
                "type",
                "finding",
                "evidence",
                "citation",
                "confidence",
                "confidence_inputs",
                "risk_impact",
                "recommendation",
                "framework_mapping",
                "alternatives_considered",
            ],
        }
    )


def parse_model_findings(
    raw_response: str,
    review_id: str,
    model_id: str,
    corpus_version: str,
    retrieved_chunk_ids: list[str],
    deterministic_rule_version: str | None,
) -> list[Finding]:
    parsed = json.loads(raw_response)
    findings = []
    for item in parsed:
        findings.append(
            Finding(
                finding_id=str(uuid.uuid4()),
                review_id=review_id,
                category=FindingCategory(item["category"]),
                type=FindingType(item["type"]),
                finding=item["finding"],
                evidence=item["evidence"],
                citation=item.get("citation"),
                confidence=item["confidence"],
                confidence_inputs=ConfidenceInputs(**item["confidence_inputs"]),
                risk_impact=item["risk_impact"],
                recommendation=item["recommendation"],
                framework_mapping=item["framework_mapping"],
                alternatives_considered=[
                    AlternativeConsidered(**a) for a in item.get("alternatives_considered", [])
                ],
                depth_level=item.get("depth_level", "lightweight"),
                model_id=model_id,
                prompt_version=PROMPT_VERSION,
                corpus_version=corpus_version,
                retrieved_chunk_ids=retrieved_chunk_ids,
                deterministic_rule_version=deterministic_rule_version,
            )
        )
    return findings


def reason_node(state: dict) -> dict:
    guardrails: GuardrailsClient = state["guardrails_client"]
    reasoning_client: BedrockReasoningClient = state["reasoning_client"]

    workload_brief = state["workload_brief"]
    if not guardrails.check(workload_brief, source="INPUT"):
        raise GuardrailBlocked("reason_input")

    retrieved_chunks = state.get("retrieved_chunks", [])
    rule_findings = state.get("rule_findings", [])
    user_content = build_user_content(workload_brief, rule_findings, retrieved_chunks)

    raw_response = reasoning_client.converse(
        system_prompt=SYSTEM_PROMPT,
        user_content=user_content,
        max_tokens=state.get("max_tokens", 4096),
    )

    findings = parse_model_findings(
        raw_response=raw_response,
        review_id=state["review_id"],
        model_id=reasoning_client.model_id,
        corpus_version=state.get("corpus_version", "unknown"),
        retrieved_chunk_ids=[c.get("chunk_id", "") for c in retrieved_chunks],
        deterministic_rule_version=state.get("deterministic_rule_version"),
    )

    return {
        **state,
        "reasoned_findings": [f.model_dump(mode="json") for f in findings],
    }
