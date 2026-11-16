"""Scorecards must not silently change cohorts, counts, history or missing costs."""

import json
from copy import deepcopy

import pytest

from scripts.evaluation_scorecard import append_scorecard, build_rows
from scripts.small_workload_eval import end_to_end_seconds, main


def report():
    slots = []
    for i, case in enumerate(["T3a", "T1-full", "T1-full", "T2-full", "T2-full"], 1):
        slots.append(
            {
                "slot": i,
                "case": case,
                "code_revision": "abc123",
                "model_id": "sonnet",
                "rule_engine_versions": ["rules@1"],
                "completed": True,
                "critical_high_caught": 2,
                "critical_high_total": 2,
                "all_caught": 3,
                "all_total": 4,
                "findings": 5,
                "false_claims": 1,
                "unsafe_fixes": 0,
                "cost_usd": 0.1,
                "cost_known": True,
                "cost_measured": True,
                "model": {"seconds": 10, "input_tokens": 100},
                "end_to_end_seconds": 30,
            }
        )
    return {
        "generated_at": "2026-11-16T00:00:00Z",
        "judging_complete": True,
        "slots": slots,
    }


def card():
    return {
        "schema": "archibrief-eval-scorecard/1",
        "case_sets": {"dev-v1": {"cases": ["T1-full", "T2-full", "T3a"]}},
        "rows": [{"id": "old", "accuracy": {"false_claims": 26}}],
    }


def options(**kwargs):
    return {"round_id": "round1", "case_set": "dev-v1", "role": "candidate", **kwargs}


def test_append_preserves_history_rates_timing_and_duplicates_fail(tmp_path):
    p = tmp_path / "scorecard.json"
    before = card()
    p.write_text(json.dumps(before))
    rows = append_scorecard(p, report(), **options())
    result = json.loads(p.read_text())
    assert result["rows"][:-1] == before["rows"]
    assert rows[0]["accuracy"]["false_claims_per_review"] == 1
    assert rows[0]["end_to_end_seconds"]["median"] == 30
    assert rows[0]["model_seconds"]["median"] == 10
    assert rows[0]["cost_usd"]["measured"] is True
    contents = p.read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        append_scorecard(p, report(), **options())
    assert p.read_bytes() == contents
    assert not p.with_name("scorecard.json.lock").exists()


def test_missing_times_costs_and_p3b_measurements_stay_unknown():
    value = report()
    for s in value["slots"]:
        s.pop("end_to_end_seconds")
        s["cost_known"] = False
        s["p3b"] = {
            "verification_calls": 1,
            "findings_removed": 2,
            "findings_changed": 0,
            "added_cost_usd": None,
            "added_seconds": None,
        }
    rows, _ = build_rows(value, card(), **options())
    row = rows[0]
    assert row["end_to_end_seconds"]["median"] is None
    assert row["cost_usd"]["total"] is None and row["cost_usd"]["measured"] is False
    assert row["p3b"]["verification_calls"] == 5
    assert row["p3b"]["findings_removed"] == 10
    assert row["p3b"]["added_cost_usd"] is None


@pytest.mark.parametrize(
    "change",
    [
        "case",
        "count",
        "unfinished",
        "negative",
        "nan",
        "narrative",
        "duplicate",
        "ambiguous_version",
        "missing_p3b",
    ],
)
def test_invalid_or_incomparable_round_is_rejected(change):
    value = report()
    slot = value["slots"][0]
    if change == "case":
        slot["case"] = "new-case"
    elif change == "count":
        value["slots"].pop()
    elif change == "unfinished":
        value["judging_complete"] = False
    elif change == "negative":
        slot["false_claims"] = -1
    elif change == "nan":
        slot["model"]["seconds"] = float("nan")
    elif change == "narrative":
        slot["code_revision"] = "Terraform secret in this text"
    elif change == "duplicate":
        value["slots"][1]["slot"] = slot["slot"]
    elif change == "ambiguous_version":
        slot["rule_engine_versions"].append("rules@2")
    elif change == "missing_p3b":
        slot["p3b"] = {}
    with pytest.raises((ValueError, KeyError)):
        build_rows(value, card(), **options())


def test_new_case_set_and_multiple_versions_need_explicit_cohorts():
    value = report()
    for s in value["slots"]:
        s["case"] = "fresh1"
    with pytest.raises(ValueError, match="register"):
        build_rows(value, card(), **options(case_set="holdout-r1"))
    rows, registry = build_rows(
        value, card(), **options(case_set="holdout-r1", register_case_set=True)
    )
    assert registry["holdout-r1"]["review_counts"] == {"fresh1": 5}
    assert len(rows) == 1
    second = deepcopy(value["slots"])
    for s in second:
        s["slot"] += 5
        s["code_revision"] = "def456"
    value["slots"] += second
    rows, _ = build_rows(
        value, card(), **options(case_set="holdout-r1", register_case_set=True)
    )
    assert len(rows) == 2


def test_cli_is_offline_and_does_not_open_aws_or_journal(tmp_path, monkeypatch):
    import boto3

    monkeypatch.setattr(
        boto3, "Session", lambda **kwargs: pytest.fail("AWS session created")
    )
    p = tmp_path / "scorecard.json"
    p.write_text(json.dumps(card()))
    r = tmp_path / "report.json"
    r.write_text(json.dumps(report()))
    assert (
        main(
            [
                "scorecard",
                "--report",
                str(r),
                "--scorecard",
                str(p),
                "--round-id",
                "r1",
                "--case-set",
                "dev-v1",
                "--role",
                "control",
            ]
        )
        == 0
    )
    assert len(json.loads(p.read_text())["rows"]) == 2


def test_end_to_end_uses_actual_timezone_timestamps_not_runtime():
    assert end_to_end_seconds("2026-11-15T23:00:00-06:00", "2026-11-16T05:01:30Z") == 90
    for start, end in [
        (None, None),
        ("bad", "bad"),
        ("2026-11-16T00:00:00", "2026-11-16T00:01:00"),
        ("2026-11-16T00:02:00Z", "2026-11-16T00:01:00Z"),
    ]:
        assert end_to_end_seconds(start, end) is None


def test_incomplete_review_can_retain_real_rule_catches_without_hiding_failure():
    value = report()
    value["slots"][0]["completed"] = False
    rows, _ = build_rows(value, card(), **options())
    assert rows[0]["failed_or_incomplete"] == 1
    assert rows[0]["accuracy"]["critical_high_caught"] == 10
    assert rows[0]["accuracy"]["false_claims_per_review"] == 1.25
