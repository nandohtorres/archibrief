"""Generic synthetic size/selection tests; no saved reviews or case outputs."""

import hashlib
from copy import deepcopy

from backend.shared.finding_verification import (
    select_verification,
    verification_input,
    verification_request_bytes,
    verify_with_dispatch,
)


def state():
    chunks = []
    findings = []
    for i in range(20):
        text = "S3 guidance preserves original versions. " * 25
        chunk = {
            "chunk_id": f"c{i}",
            "text": text,
            "source_url": "https://docs.aws.amazon.com/example",
            "document_id": "d1",
            "content_hash": hashlib.sha256(text.encode()).hexdigest(),
            "parser_version": "p1",
            "corpus_version": "corpus1",
            "retrieved_at": "2026-11-16T00:00:00Z",
        }
        chunks.append(chunk)
        if i < 12:
            findings.append(
                {
                    "finding_id": f"f{i:02}",
                    "type": "inference",
                    "category": "backup",
                    "model_id": "synthetic",
                    "finding": f"aws_s3_bucket.store_{i} needs protection",
                    "evidence": f"aws_s3_bucket.store_{i} declares suspended versioning",
                    "risk_impact": "Original versions may be lost",
                    "recommendation": f"Review versioning on store_{i}",
                    "citation": {
                        **{k: v for k, v in chunk.items() if k != "text"},
                        "exact_text_span": "S3 guidance",
                    },
                    "plain": {
                        "action": "Confirm the versioning change",
                        "analogy": "NOT_SENT" * 1000,
                        "written_by": "model",
                        "needs_action": True,
                        "severity": "high",
                    },
                    "alternatives_considered": [{"option": "NOT_SENT" * 1000}],
                    "confidence_inputs": {"large": "NOT_SENT" * 1000},
                    "retrieved_chunk_ids": [c["chunk_id"] for c in chunks],
                }
            )
    return {
        "workload_brief": "Synthetic version recovery requirements",
        "preflight_fields": {},
        "terraform_resources": {
            "resources": [
                {
                    "type": "aws_s3_bucket",
                    "name": f"store_{i}",
                    "settings": {"versioning": "Suspended", "description": "D" * 1600},
                }
                for i in range(20)
            ]
        },
        "retrieved_chunks": chunks,
        "reasoned_findings": findings,
    }


def test_twenty_resources_twelve_candidates_fit_under_sixty_k_without_ancillary_fields():
    value = state()
    before = deepcopy(value)
    supplied = verification_input(value, value["reasoned_findings"])
    assert verification_request_bytes(supplied) < 60000
    assert len(supplied["evidence"]) == 12
    assert len([key for key in supplied["facts"] if key.startswith("resource:")]) == 12
    claim = supplied["candidates"][0]
    assert "alternatives_considered" not in claim and "confidence_inputs" not in claim
    assert (
        "plain" not in claim
        and claim["plain_action"] == "Confirm the versioning change"
    )
    assert set(claim["citation"]) == {"chunk_id", "exact_text_span"}
    assert value == before


def test_resource_selection_keeps_one_reference_step_in_both_directions_not_two():
    value = state()
    value["reasoned_findings"] = value["reasoned_findings"][:1]
    resources = value["terraform_resources"]["resources"]
    resources[0]["settings"]["peer"] = "${aws_s3_bucket.store_1.id}"
    resources[1]["settings"]["peer"] = "${aws_s3_bucket.store_2.id}"
    resources[3]["settings"]["peer"] = "${aws_s3_bucket.store_0.id}"
    selected = verification_input(value, value["reasoned_findings"])["facts"]
    assert "resource:aws_s3_bucket.store_1" in selected
    assert "resource:aws_s3_bucket.store_3" in selected
    assert "resource:aws_s3_bucket.store_2" not in selected


def test_size_selection_prefers_highest_severity_and_never_discards_unchecked_findings():
    value = state()
    value["reasoned_findings"] = value["reasoned_findings"][:2]
    low, critical = value["reasoned_findings"]
    low["plain"]["severity"] = "low"
    critical["plain"]["severity"] = "critical"
    limit = verification_request_bytes(verification_input(value, [critical]))
    chosen, skipped = select_verification(
        value, value["reasoned_findings"], byte_limit=limit
    )
    assert [c["finding_id"] for c in chosen] == [critical["finding_id"]]
    assert skipped == {low["finding_id"]: "request_size"}
    assert len(value["reasoned_findings"]) == 2


def test_still_oversized_input_plans_no_call_and_retains_all_original_claims():
    value = state()
    for chunk in value["retrieved_chunks"]:
        chunk["text"] += "Q" * 100000
        chunk["content_hash"] = hashlib.sha256(chunk["text"].encode()).hexdigest()
    for finding, chunk in zip(
        value["reasoned_findings"], value["retrieved_chunks"], strict=False
    ):
        finding["citation"]["content_hash"] = chunk["content_hash"]
    original = deepcopy(value["reasoned_findings"])
    chosen, skipped = select_verification(value, original)
    assert not chosen and set(skipped.values()) == {"request_size"}

    def forbidden(**kwargs):
        raise AssertionError("No call should fit")

    result = verify_with_dispatch(value, forbidden)
    assert result["reasoned_findings"] == original
    assert {
        c["reason_code"] for c in result["additional_verification"]["findings"]
    } == {"request_size"}


def test_product_checks_the_subset_that_fits_and_keeps_the_oversized_finding():
    import json

    value = state()
    large = value["retrieved_chunks"][0]
    large["text"] += "Q" * 100000
    large["content_hash"] = hashlib.sha256(large["text"].encode()).hexdigest()
    value["reasoned_findings"][0]["citation"]["content_hash"] = large["content_hash"]
    value["reasoned_findings"][0]["plain"]["severity"] = "critical"
    original = deepcopy(value["reasoned_findings"])
    calls = []

    def dispatch(**kwargs):
        supplied = json.loads(kwargs["user_content"])
        calls.append(supplied)
        return {
            "verdicts": [
                {
                    "finding_id": c["finding_id"],
                    "verdict": "supported",
                    "fact_ids": [
                        f"resource:aws_s3_bucket.store_{int(c['finding_id'][1:])}"
                    ],
                    "evidence_ids": [c["citation"]["chunk_id"]],
                    "remediation_applicable": True,
                    "reason": "Synthetic supported control",
                }
                for c in supplied["candidates"]
            ]
        }

    result = verify_with_dispatch(value, dispatch)
    assert len(calls) == 1 and len(calls[0]["candidates"]) == 11
    assert "c0" not in calls[0]["evidence"]
    assert result["reasoned_findings"] == original
    checks = {r["finding_id"]: r for r in result["additional_verification"]["findings"]}
    assert checks["f00"]["reason_code"] == "request_size"
    assert checks["f01"]["status"] == "supported"
