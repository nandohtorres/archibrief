"""P1 regression guards (plan Step 0). See tests/backend/p1_guards.py.

Known defects are strict xfails: the test fails the moment a fix lands, which
forces the marker (and, for the Lambda URL, the UNRESOLVED_GAPS entry in the
adversarial suite) to be removed in the same change.
"""

from __future__ import annotations

import re

import pytest
from scripts.small_workload_eval import CORPUS, case_by_id, load_manifest

from tests.backend.adversarial.harness import trivy_path
from tests.backend.p1_guards import (
    CASE_ISSUES,
    JUDGED_CAUGHT,
    MUST_FIND,
    assert_issues_preserved,
    covered_issues,
    load_recorded,
    replay_case,
    violations,
)

TRIVY = trivy_path()
needs_trivy = pytest.mark.skipif(TRIVY is None, reason="Trivy not installed (set TRIVY_PATH)")

CASES = case_by_id(load_manifest())
SLOT_CASE = {1: "T1-small", 2: "T1-full", 3: "T2-small", 4: "T2-full", 5: "T3a"}


@pytest.fixture(scope="module")
def replays():
    cache: dict[str, object] = {}

    def get(case_id: str):
        if case_id not in cache:
            cache[case_id] = replay_case(CASES[case_id], CORPUS, TRIVY)
        return cache[case_id]

    return get


def _rows(kind: str):
    for case_id, issues in CASE_ISSUES.items():
        for issue_id, issue in issues.items():
            if kind == "rule" and issue.rule and not issue.rule_gap:
                yield pytest.param(case_id, issue_id, id=f"{case_id}-{issue_id}")
            if kind == "fact":
                yield pytest.param(case_id, issue_id, id=f"{case_id}-{issue_id}")
            if kind == "gap" and issue.rule_gap:
                yield pytest.param(case_id, issue_id, id=f"{case_id}-{issue_id}")


# ------------------------------------------------- offline deterministic stages


@needs_trivy
@pytest.mark.parametrize("case_id", sorted(CASE_ISSUES))
def test_parser_counts_match_the_frozen_manifest(case_id, replays):
    scope = replays(case_id).parsed["review_scope"]
    assert scope["state"] == "recorded"
    assert scope["known_y"] == CASES[case_id]["known_declarations"]


@needs_trivy
@pytest.mark.parametrize(("case_id", "issue_id"), list(_rows("rule")))
def test_a_deterministic_rule_catches_each_issue_it_used_to(case_id, issue_id, replays):
    concern, name = CASE_ISSUES[case_id][issue_id].rule
    assert replays(case_id).rule_catches(concern, name), (
        f"{issue_id}: rule {concern!r} no longer reports {name!r}"
    )


@needs_trivy
@pytest.mark.parametrize(("case_id", "issue_id"), list(_rows("fact")))
def test_the_model_input_carries_the_fact_behind_each_issue(case_id, issue_id, replays):
    replay = replays(case_id)
    for fact in CASE_ISSUES[case_id][issue_id].facts:
        assert replay.fact(fact.type, fact.name, fact.setting) == fact.value, (
            f"{issue_id}: {fact.type}.{fact.name} {fact.setting}"
        )


@needs_trivy
@pytest.mark.xfail(strict=True, reason="F07-D-03: no deterministic rule for a public Lambda URL")
@pytest.mark.parametrize(("case_id", "issue_id"), list(_rows("gap")))
def test_a_rule_reports_the_public_lambda_url(case_id, issue_id, replays):
    name = CASE_ISSUES[case_id][issue_id].resource
    assert any(
        re.search(r"function url", f["finding"], re.IGNORECASE)
        and name in f["finding"] + f["evidence"]
        for f in replays(case_id).rules
    )


@needs_trivy
@pytest.mark.parametrize(
    ("case_id", "name"),
    [("T2-small", "evidence"), ("T2-full", "evidence"), ("T1-full", "vendor_catalog")],
)
def test_an_empty_lifecycle_prefix_covers_all_objects(case_id, name, replays):
    value = replays(case_id).fact(
        "aws_s3_bucket_lifecycle_configuration", name, "rule[0].filter_scope"
    )
    assert value == "all_objects"


# ------------------------------------------------------ recorded model reviews


@pytest.mark.parametrize("slot", sorted(SLOT_CASE))
def test_recorded_coverage_matches_the_judged_baseline(slot):
    recorded = load_recorded(slot)
    issues = CASE_ISSUES[recorded["case"]]
    assert covered_issues(recorded["findings"], issues) == JUDGED_CAUGHT[slot]


def test_recorded_must_find_recall_is_29_of_31():
    caught = total = 0
    for slot, case_id in SLOT_CASE.items():
        issues = CASE_ISSUES[case_id]
        must = {i for i, issue in issues.items() if issue.severity in MUST_FIND}
        total += len(must)
        caught += len(must & covered_issues(load_recorded(slot)["findings"], issues))
    assert (caught, total) == (29, 31)


KNOWN_VIOLATIONS = {
    1: {"ineffective_url_fix": "96c9681b"},
    2: {"false_lifecycle_scope": "347aeab1"},
    3: {},
    4: {"retention_removal_fix": "86278027"},
    5: {},
}


@pytest.mark.parametrize("slot", sorted(KNOWN_VIOLATIONS))
def test_detectors_flag_exactly_the_known_defects_in_the_recorded_reviews(slot):
    found = violations(load_recorded(slot)["findings"])
    assert {k: [i[:8] for i in ids] for k, ids in found.items()} == {
        k: [v] for k, v in KNOWN_VIOLATIONS[slot].items()
    }


def test_a_clean_report_trips_no_detector():
    assert violations(load_recorded(3)["findings"] + load_recorded(5)["findings"]) == {}


# ------------------------------------------------------- the merge invariant


def test_identity_preserves_every_issue():
    for slot, case_id in SLOT_CASE.items():
        findings = load_recorded(slot)["findings"]
        assert_issues_preserved(findings, findings, CASE_ISSUES[case_id])


def test_pitr_is_found_only_by_the_deterministic_rule_in_every_recorded_review():
    """The dependency a de-duplication must respect: the model never states
    point-in-time recovery, so the rule finding is the only cover."""
    for slot in (3, 4, 5):
        recorded = load_recorded(slot)
        issues = CASE_ISSUES[recorded["case"]]
        issue = issues["T2-03" if "T2-03" in issues else "T3A-DATA-03"]
        from tests.backend.p1_guards import covers

        covering = [f for f in recorded["findings"] if covers(f, issue)]
        assert covering
        assert {f["type"] for f in covering} == {"deterministic-rule-result"}


def test_dropping_the_only_pitr_finding_is_caught():
    recorded = load_recorded(5)
    issues = CASE_ISSUES["T3a"]
    after = [f for f in recorded["findings"] if f.get("concern") != "dynamodb_pitr"]
    with pytest.raises(AssertionError, match="T3A-DATA-03"):
        assert_issues_preserved(recorded["findings"], after, issues)


def test_dropping_a_duplicate_whose_rule_remains_is_allowed():
    """The model's own IAM `*` finding duplicates the rule finding; removing
    the model copy loses nothing because the rule still covers the issue."""
    recorded = load_recorded(5)
    after = [
        f
        for f in recorded["findings"]
        if not (
            f["type"] != "deterministic-rule-result" and "Action * on Resource *" in f["finding"]
        )
    ]
    assert len(after) < len(recorded["findings"])
    assert_issues_preserved(recorded["findings"], after, CASE_ISSUES["T3a"])
