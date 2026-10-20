"""Validate reason_node end-to-end against real Bedrock.

Sibling to backend/corpus/validate_retrieve_node.py — same convention: not
a pytest test, run directly with real AWS credentials, near-zero cost
(one embed call, one vector query, one Claude Converse call, one
ApplyGuardrail call).

Builds real retrieved_chunks via retrieve_node first (same pattern as
validate_retrieve_node.py), then feeds them into reason_node with a real
GuardrailsClient (the deployed prompt-attack guardrail, ADR-0033) and a
real BedrockReasoningClient, and reports the full raw + parsed output.
"""

from __future__ import annotations

import json
import os
import uuid

from backend.agent.nodes.reason import (
    FindingValidationError,
    call_reasoning_model,
    parse_model_findings,
    resolve_rule_findings,
)
from backend.agent.nodes.retrieve import retrieve_node
from backend.corpus.lexical_index import build_lexical_corpus_index_from_disk
from backend.shared.clients import (
    BedrockEmbeddingClient,
    BedrockReasoningClient,
    GuardrailsClient,
    S3VectorsClient,
)

_VECTOR_BUCKET_NAME = os.environ.get("ARCHIBRIEF_VECTOR_BUCKET", "archibrief-dev-kb")
_VECTOR_INDEX_NAME = os.environ.get("ARCHIBRIEF_VECTOR_INDEX", "archibrief-dev-kb-index")
_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Real value lives in module.guardrails.aws_bedrock_guardrail.prompt_attack's
# output — not hardcoded here so this file stays safe to commit; export
# ARCHIBRIEF_GUARDRAIL_ID before running (see infra/modules/guardrails/outputs.tf).
_GUARDRAIL_ID = os.environ.get("ARCHIBRIEF_GUARDRAIL_ID", "")
_GUARDRAIL_VERSION = os.environ.get("ARCHIBRIEF_GUARDRAIL_VERSION", "1")

# Hardcoded for this manual script; runtime_entrypoint.py reads the model ID
# from ARCHIBRIEF_REASONING_MODEL_ID instead.
_MODEL_ID = "us.anthropic.claude-sonnet-4-6"

_WORKLOAD_BRIEF = (
    "We run a single S3 bucket ('customer-records-prod') that stores critical "
    "customer PII and billing records for a small SaaS product. The bucket has "
    "no versioning enabled, and the AWS account's root user does not have MFA "
    "configured. There is no CloudTrail trail in the account. The application "
    "backend is a single Lambda function reading/writing directly to this bucket."
)

_RETRIEVAL_QUERY = (
    "S3 bucket versioning for critical data recovery and root user MFA best practices"
)

_RULE_FINDINGS = [
    {
        "finding_id": str(uuid.uuid4()),
        "review_id": "validate-reason-node-run",
        "category": "recovery",
        "type": "deterministic-rule-result",
        "finding": "S3 bucket 'customer-records-prod' does not have versioning enabled",
        "evidence": (
            'resource "aws_s3_bucket" "customer-records-prod" found with no '
            "enabled versioning configuration"
        ),
        "citation": None,
        "confidence": 1.0,
        "confidence_inputs": {
            "evidence_directness": 1.0,
            "source_agreement": 1.0,
            "rule_determinism": 1.0,
        },
        "risk_impact": "Accidental or malicious object deletion/overwrite cannot be recovered.",
        "recommendation": 'Enable aws_s3_bucket_versioning with status = "Enabled".',
        "framework_mapping": ["AWS Well-Architected: Reliability Pillar"],
        "alternatives_considered": [],
        "depth_level": "lightweight",
        "deterministic_rule_version": "rule_engine@2026-09-08",
    }
]


def main() -> None:
    review_id = f"validate-reason-node-{uuid.uuid4().hex[:8]}"

    embedding_client = BedrockEmbeddingClient(region_name=_REGION)
    vectors_client = S3VectorsClient(
        bucket_name=_VECTOR_BUCKET_NAME, index_name=_VECTOR_INDEX_NAME, region_name=_REGION
    )
    lexical_corpus_index = build_lexical_corpus_index_from_disk()

    retrieve_state = {
        "retrieval_query": _RETRIEVAL_QUERY,
        "embedding_client": embedding_client,
        "vectors_client": vectors_client,
        "lexical_corpus_index": lexical_corpus_index,
    }
    retrieve_result = retrieve_node(retrieve_state)
    retrieved_chunks = retrieve_result["retrieved_chunks"]

    print(f"retrieved {len(retrieved_chunks)} chunks for query: {_RETRIEVAL_QUERY!r}")
    for chunk in retrieved_chunks:
        print(f"  - {chunk['chunk_id']} (match_type={chunk['match_type']}, score={chunk['score']})")
    print()

    guardrails_client = GuardrailsClient(
        guardrail_id=_GUARDRAIL_ID, guardrail_version=_GUARDRAIL_VERSION, region_name=_REGION
    )
    reasoning_client = BedrockReasoningClient(model_id=_MODEL_ID, region_name=_REGION)

    allowed = guardrails_client.check(_WORKLOAD_BRIEF, source="INPUT")
    print(f"guardrails.check(workload_brief) -> {allowed}")
    if not allowed:
        print("BLOCKED by guardrails — stopping (matches reason_node's GuardrailBlocked path).")
        return

    corpus_version = retrieved_chunks[0]["corpus_version"] if retrieved_chunks else "unknown"

    raw_findings = call_reasoning_model(
        reasoning_client=reasoning_client,
        workload_brief=_WORKLOAD_BRIEF,
        rule_findings=_RULE_FINDINGS,
        retrieved_chunks=retrieved_chunks,
        # Forced tool-use output is more verbose than free-text JSON (every
        # required field on every finding), and this brief produces enough
        # findings to exceed 4096. 8192 is the standard Claude Sonnet output
        # ceiling on Bedrock without an extended-output beta header.
        max_tokens=8192,
    )

    print("=== RAW model tool-call findings ===")
    print(json.dumps(raw_findings, indent=2, default=str))
    print()

    try:
        model_findings = parse_model_findings(
            raw_findings=raw_findings,
            review_id=review_id,
            model_id=reasoning_client.model_id,
            corpus_version=corpus_version,
            retrieved_chunks=retrieved_chunks,
            deterministic_rule_version="rule_engine@2026-09-08",
        )
    except FindingValidationError as exc:
        print("=== FINDING VALIDATION FAILED ===")
        for failure in exc.failures:
            print(f"  - {failure}")
        return

    if not model_findings:
        # Not necessarily wrong (a genuinely clean workload could produce
        # zero model findings), but for THIS scripted workload brief
        # (multiple real deficiencies described) zero is suspicious enough
        # to flag loudly rather than let a silent empty success pass by
        # unnoticed.
        print(
            "=== WARNING: model returned zero findings for a workload brief that "
            "describes multiple real deficiencies — investigate before trusting this run ==="
        )

    rule_findings = resolve_rule_findings(_RULE_FINDINGS)
    findings = rule_findings + model_findings

    print(
        f"=== {len(rule_findings)} rule-engine finding(s) + {len(model_findings)} "
        f"model finding(s), citations server-verified ==="
    )
    print(json.dumps([f.model_dump(mode="json") for f in findings], indent=2, default=str))


if __name__ == "__main__":
    main()
