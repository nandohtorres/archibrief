"""Synthetic fail-check side-channel contracts; no evaluation artifacts."""

import json
from copy import deepcopy

import pytest

from backend.agent.nodes.reason import verify_model_findings
from backend.chat.context import build_review_context
from backend.lambdas.finalize.handler import assemble_evidence_ledger
from backend.lambdas.validate.handler import handler as validate
from backend.shared.report import build_review_report
from backend.shared.unverified import (
    unverified_finding,
    unverified_findings,
)
from tests.backend.agent.nodes.test_reason import _chunk, _valid_finding_item

CHUNK = _chunk("chunk-a", "Encrypt data at rest using AWS KMS customer managed keys.")


@pytest.mark.parametrize(
    "overrides,code",
    [
        ({"chunk_id": "foreign"}, "chunk_not_retrieved"),
        ({"exact_quote": "not in this passage"}, "quote_not_in_chunk"),
        ({"chunk_id": None}, "chunk_missing"),
        ({"exact_quote": ""}, "quote_missing"),
        ({"category": "invented"}, "invalid_fields"),
        ({"confidence": 4}, "invalid_fields"),
        ({"type": "invalid"}, "invalid_type"),
        (
            {
                "finding": "The Lambda has a public function URL and runs outside any VPC.",
                "recommendation": "Attach the function to the workload VPC and add a VPC endpoint.",
            },
            "wrong_fix",
        ),
        (
            {"recommendation": "Shrink the EBS volume in place."},
            "unsupported_remediation",
        ),
    ],
)
def test_failed_claims_are_retained_without_fixes_or_bad_citations(overrides, code):
    original = [_valid_finding_item(**overrides), _valid_finding_item()]
    before = deepcopy(original)
    unverified = []
    accepted, errors = verify_model_findings(
        original, "synthetic", "fake", "c1", [CHUNK], None, unverified=unverified
    )
    assert len(accepted) == 1 and len(errors) == 1
    assert len(unverified) == 1 and unverified[0]["reason_code"] == code
    assert unverified[0]["finding"] == original[0]["finding"]
    assert unverified[0]["recommendation_withheld"] is True
    assert not {
        "recommendation",
        "plain",
        "citation",
        "alternatives_considered",
        "risk_impact",
    }.intersection(unverified[0])
    assert original == before


def test_unverified_record_is_bounded_and_does_not_trust_shapes_or_reason_text():
    raw = {
        "finding": "F" * 10000,
        "evidence": "E" * 10000,
        "category": {},
        "reason_code": {},
        "reason": "unsafe reason",
        "recommendation": "WITHHELD",
        "plain": {"action": "WITHHELD"},
    }
    value = unverified_finding(raw, {})
    assert len(value["finding"]) == 1200 and len(value["evidence"]) == 1600
    assert value["category"] is None and value["reason_code"] == "other"
    assert "WITHHELD" not in json.dumps(value) and "unsafe reason" not in json.dumps(
        value
    )
    assert len(unverified_findings([value] * 100)) == 100
    assert unverified_findings(None) == []


def test_validate_ledger_report_and_chat_keep_unverified_separate():
    accepted, _ = verify_model_findings(
        [_valid_finding_item()], "synthetic", "fake", "c1", [CHUNK], None
    )
    good = accepted[0].model_dump(mode="json")
    bad = {
        **good,
        "finding_id": "bad",
        "confidence": 9,
        "finding": "UNVERIFIED_ONLY aws_db_instance.db",
        "recommendation": "WITHHELD_ACTION",
        "plain": {"action": "WITHHELD_ACTION"},
    }
    event = validate({"findings": [good, bad]}, None)
    assert len(event["valid_findings"]) == 1 and event["rejected_count"] == 1
    assert (
        event["unverified_findings"][0]["reason"]
        == "The finding failed the format check."
    )
    ledger = assemble_evidence_ledger(
        "synthetic", accepted, unverified=event["unverified_findings"]
    )
    assert (
        ledger["finding_count"] == 1
        and len(ledger["findings_by_category"]["encryption"]) == 1
    )
    report = build_review_report({"reviewId": "synthetic"}, ledger)
    assert len(report["findings"]) == 1 and len(report["unverified_findings"]) == 1
    assert "WITHHELD_ACTION" not in json.dumps(report)
    assert "UNVERIFIED_ONLY" not in build_review_context(ledger).cached_text()


def test_revalidation_never_resurrects_disallowed_fields_and_public_prices_are_removed():
    entry = unverified_finding(
        {
            "finding": "Inspect aws_db_instance.db for $120/month",
            "evidence": "${var.keep} $1",
        },
        "wrong_fix",
    )
    event = validate(
        {
            "findings": [],
            "unverified_findings": [
                {
                    **entry,
                    "recommendation": "WITHHELD",
                    "citation": {"exact_text_span": "WITHHELD"},
                }
            ],
        },
        None,
    )
    ledger = assemble_evidence_ledger(
        "synthetic", [], unverified=event["unverified_findings"]
    )
    report = build_review_report({"reviewId": "synthetic"}, ledger)
    assert report["findings"] == [] and ledger["finding_count"] == 0
    assert "WITHHELD" not in json.dumps(report) and "$120" not in json.dumps(report)
    assert report["unverified_findings"][0]["evidence"] == "${var.keep} $1"
    assert report["unverified_findings"][0]["resource"] == "aws_db_instance.db"


def test_cached_chat_notes_are_cleaned_without_mutating_storage():
    from backend.chat.access import transcript_item
    from backend.chat.verify import VerifiedAnswer
    from backend.lambdas.ask_question.handler import _answer_fields

    answer = VerifiedAnswer(
        "answered",
        None,
        [{"text": "Cited answer", "citations": []}],
        unsupported=["Unsupported $250/month text"],
    )
    stored = {"questionKey": "Q#synthetic", **_answer_fields(answer)}
    before = deepcopy(stored)
    public = transcript_item(stored)
    assert public["unsupported"] and "$250" not in str(public["unsupported"])
    assert public["answer"][0]["text"] == "Cited answer"
    assert stored == before


def test_deeper_unverified_claims_are_projected_without_entering_findings():
    from backend.shared.review_projection import assemble_current_ledger
    from tests.backend.shared.test_review_projection import _record

    ledger = {"findings": [_record()]}
    marker = {
        "reviewId": "r1",
        "kind": "deeper-result",
        "parent_finding_id": "base",
        "finding_ids": [],
        "ttl": 1000,
        "unverified_findings": [
            {
                "finding": "DEEP_UNVERIFIED_ONLY",
                "reason_code": "invalid_fields",
                "recommendation": "WITHHELD",
            }
        ],
    }
    current = assemble_current_ledger(ledger, "r1", [marker], now=100)
    assert current["finding_count"] == 1 and len(current["unverified_findings"]) == 1
    assert "WITHHELD" not in json.dumps(current["unverified_findings"])
    foreign = {**marker, "reviewId": "other"}
    assert (
        assemble_current_ledger(ledger, "r1", [foreign], now=100)["unverified_findings"]
        == []
    )


@pytest.mark.parametrize(
    "item,rules,code",
    [
        (
            _valid_finding_item(
                finding="aws_kms_key.example is unused",
                recommendation="Delete the KMS key.",
            ),
            [],
            "remediation_contradiction",
        ),
        (
            _valid_finding_item(
                finding="The failed DLQ retention is too short",
                recommendation="Set the failed DLQ retention to one day.",
            ),
            [
                {
                    "concern": "sqs_dlq_retention",
                    "finding": "Dead-letter queue 'failed' expires messages too early",
                }
            ],
            "rule_owned_remediation",
        ),
    ],
)
def test_other_fix_failures_also_withhold_actions(item, rules, code):
    unverified = []
    accepted, failures = verify_model_findings(
        [item],
        "synthetic",
        "fake",
        "c1",
        [CHUNK],
        None,
        authoritative_rule_findings=rules,
        unverified=unverified,
    )
    assert not accepted and failures
    assert unverified[0]["reason_code"] == code
    assert "recommendation" not in unverified[0]
