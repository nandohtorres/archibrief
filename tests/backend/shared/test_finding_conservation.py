"""Synthetic conservation tests: all authorized claims survive classification."""

import json
from collections import Counter
from copy import deepcopy

import pytest

from backend.agent.nodes.reason import MAX_MODEL_FINDINGS, reason_node
from backend.agent.nodes.verify_findings import verify_findings_node
from backend.chat.context import build_review_context
from backend.lambdas.finalize.handler import assemble_evidence_ledger
from backend.lambdas.validate.handler import handler as validate
from backend.shared.models.finding import Finding
from backend.shared.report import build_review_report
from backend.shared.review_projection import assemble_current_ledger
from backend.shared.unverified import (
    evidence_reference,
    unverified_finding,
    unverified_findings,
)
from tests.backend.agent.nodes.test_reason import _reason_state, _valid_finding_item
from tests.backend.agent.test_verify_findings import state, verdict
from tests.backend.shared.test_review_projection import _item, _record


def identifiers(result):
    return Counter(
        f["finding_id"]
        for section in (
            "reasoned_findings",
            "unverified_findings",
            "disproved_findings",
        )
        for f in result.get(section, [])
    )


@pytest.mark.parametrize(
    "response",
    [
        TimeoutError(),
        {},
        {"verdicts": []},
        {"verdicts": [verdict(verdict="contradicted", evidence_ids=[])]},
        {"verdicts": [verdict(verdict="insufficient_evidence")]},
        {"verdicts": [verdict(remediation_applicable=False)]},
        {"verdicts": [verdict(fact_ids=["foreign"])]},
        {"verdicts": [verdict(), verdict()]},
    ],
)
def test_verification_preserves_every_input_occurrence_and_existing_sections(response):
    value = state(response)
    value["unverified_findings"] = [
        unverified_finding({"finding_id": "prior"}, "other")
    ]
    expected = identifiers(value)
    result = verify_findings_node(value)
    assert identifiers(result) == expected
    assert result["additional_verification"]["suppressed"] == 0
    assert result["reasoned_findings"] == [value["reasoned_findings"][0]]
    assert "recommendation" not in json.dumps(
        result["unverified_findings"] + result["disproved_findings"]
    ).replace("recommendation_withheld", "")


def test_duplicate_identifiers_keep_both_occurrences_without_requesting_ambiguous_verdicts():
    value = state()
    value["reasoned_findings"].append(deepcopy(value["reasoned_findings"][-1]))
    expected = identifiers(value)
    result = verify_findings_node(value)
    assert identifiers(result) == expected
    assert len(result["unverified_findings"]) == 2
    assert value["reasoning_client"].calls == 0


def test_reason_cap_preserves_occurrences_even_when_the_same_object_is_repeated():
    item = _valid_finding_item()
    result = reason_node(_reason_state([item] * (MAX_MODEL_FINDINGS + 30)))
    assert len(result["reasoned_findings"]) == MAX_MODEL_FINDINGS
    assert len(result["unverified_findings"]) == 30
    assert all(f["reason_code"] == "model_limit" for f in result["unverified_findings"])


def test_validate_and_publication_preserve_duplicate_invalid_and_disproved_claims():
    good = _record()
    invalid = {**good, "finding_id": "invalid", "confidence": 9}
    disproved = unverified_finding(
        {
            "finding_id": "disproved",
            "finding": "DISPROVED_ONLY",
            "recommendation": "UNSAFE",
        },
        "contradicted",
        contradicting=[evidence_reference("resource:test", "fact", {"enabled": True})],
        checks=[{"name": "verification", "status": "failed"}],
    )
    checked = validate(
        {"findings": [good, good, invalid], "disproved_findings": [disproved]}, None
    )
    ledger = assemble_evidence_ledger(
        "r1",
        [Finding.model_validate(f) for f in checked["valid_findings"]],
        unverified=checked["unverified_findings"],
        disproved=checked["disproved_findings"],
    )
    report = build_review_report({"reviewId": "r1"}, ledger)
    assert ledger["finding_count"] == 1 and len(report["findings"]) == 1
    assert len(report["unverified_findings"]) == 2
    assert len(report["disproved_findings"]) == 1
    assert report["disproved_findings"][0]["contradicting_evidence"][0]["text"]
    assert "DISPROVED_ONLY" not in build_review_context(ledger).cached_text()
    assert "UNSAFE" not in json.dumps(report)


def test_projection_preserves_authorized_duplicates_orphans_and_incomplete_children():
    marker = {
        "reviewId": "r1",
        "kind": "deeper-result",
        "parent_finding_id": "base",
        "finding_ids": ["child", "missing"],
        "ttl": 1000,
    }
    current = assemble_current_ledger(
        {"findings": [_record()]},
        "r1",
        [_item(), _item(), _item("orphan", parent_finding_id="missing"), marker],
        now=100,
    )
    assert current["finding_count"] == 1
    assert Counter(f["reason_code"] for f in current["unverified_findings"]) == {
        "duplicate_finding": 1,
        "parent_unverified": 1,
        "incomplete_batch": 1,
    }


def test_fact_only_contradiction_exposes_pinned_fact_without_claiming_a_quote_check():
    value = state({"verdicts": [verdict(verdict="contradicted", evidence_ids=[])]})
    value["reasoned_findings"][-1]["citation"] = None
    value["reasoned_findings"][-1]["type"] = "not-observable"
    result = verify_findings_node(value)
    record = result["disproved_findings"][0]
    assert record["contradicting_evidence"][0]["kind"] == "fact"
    assert record["supporting_evidence"] == []
    assert {c["name"]: c["status"] for c in record["checks"]}["citation"] == "not-run"


def test_evidence_metadata_survives_reprojection_and_marks_clipping_honestly():
    entry = unverified_finding(
        {"finding_id": "x", "exact_quote": "Unconfirmed submitted quote"},
        "wrong_fix",
        supporting=[{"id": "c1", "kind": "passage", "text": "x" * 3000}],
        checks=[
            {"name": "citation", "status": "passed"},
            {"name": "format", "status": []},
        ],
    )
    record = unverified_findings([entry])[0]
    assert record["supporting_evidence"][0]["truncated"] is True
    assert record["checks"] == [{"name": "citation", "status": "passed"}]
    assert record["submitted_quote"] == "Unconfirmed submitted quote"


def test_projection_keeps_orphan_marker_claims_but_never_foreign_or_expired_rows():
    marker = {
        "reviewId": "r1",
        "kind": "deeper-result",
        "parent_finding_id": "missing",
        "finding_ids": [],
        "ttl": 1000,
        "unverified_findings": [
            unverified_finding({"finding_id": "orphan-claim"}, "other")
        ],
    }
    current = assemble_current_ledger(
        {"findings": [_record()]},
        "r1",
        [
            marker,
            {**marker, "reviewId": "foreign"},
            {**marker, "ttl": 1},
            _item("foreign", review_id="other", confidence=9),
        ],
        now=100,
    )
    assert [f["finding_id"] for f in current["unverified_findings"]] == ["orphan-claim"]
