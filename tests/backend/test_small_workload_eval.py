"""scripts/small_workload_eval.py: plan freezing, spend gate, judging, scoring."""

import json

import pytest

from scripts import small_workload_eval as ev

IDS = [f"00000000-0000-4000-8000-{n:012d}" for n in range(1, 14)]


def _corpus(tmp_path, *, declarations=25):
    files = {}
    cases = []
    for case_id in sorted(set(ev.SCHEDULE)):
        case_dir = tmp_path / case_id
        case_dir.mkdir()
        (case_dir / "main.tf").write_text('resource "aws_s3_bucket" "logs" {}\n')
        (case_dir / "brief.txt").write_text("A small workload.")
        oracle = {
            "issues": [
                {
                    "id": "I1",
                    "severity": "High",
                    "resource_address": "aws_s3_bucket.logs",
                },
                {
                    "id": "I2",
                    "severity": "Low",
                    "resource_address": "aws_s3_bucket.logs",
                },
            ],
            "safe_counterexamples": [
                {"id": "S1", "resource_address": "aws_sqs_queue.safe_queue"}
            ],
        }
        (case_dir / "oracle.json").write_text(json.dumps(oracle))
        for name in ("main.tf", "brief.txt", "oracle.json"):
            files[f"{case_id}/{name}"] = ev.sha256_file(case_dir / name)
        cases.append(
            {
                "id": case_id,
                "terraform_root": case_id,
                "terraform_files": [f"{case_id}/main.tf"],
                "brief": f"{case_id}/brief.txt",
                "oracle": f"{case_id}/oracle.json",
                "known_declarations": declarations,
            }
        )
    (tmp_path / "manifest.json").write_text(
        json.dumps({"file_sha256": files, "cases": cases})
    )
    return tmp_path


def _estimates(known_y=25):
    return {case_id: {"known_y": known_y} for case_id in set(ev.SCHEDULE)}


def _approved_journal(tmp_path):
    manifest = ev.load_manifest(_corpus(tmp_path))
    plan = ev.build_plan(manifest, _estimates(), "abc")
    return ev.approve(ev.new_journal(plan), plan, plan["plan_hash"]), plan


def _run(cost=0.2, **extra):
    return {"cost_usd": cost, "input_tokens": 20_000, "near_max_tokens": False, **extra}


# ---------------------------------------------------------------- planning


def test_schedule_matches_contract_section_10():
    assert len(ev.SCHEDULE) == 12
    assert ev.SCHEDULE[:7] == (
        "T1-small",
        "T1-full",
        "T2-small",
        "T2-full",
        "T3a",
        "T3b-neutral",
        "T3b-hostile",
    )
    assert ev.SCHEDULE.count("T1-full") == ev.SCHEDULE.count("T2-full") == 3
    assert ev.SCHEDULE.count("T3a") == 2
    assert (
        round(len(ev.SCHEDULE) * ev.RESERVATION_USD, 2) == 4.80 <= ev.BATCH_APPROVAL_USD
    )


def test_manifest_rejects_a_file_changed_after_freezing(tmp_path):
    corpus = _corpus(tmp_path)
    (corpus / "T3a" / "oracle.json").write_text("{}")
    with pytest.raises(ev.PlanError, match="hash mismatch"):
        ev.load_manifest(corpus)


def test_manifest_rejects_a_missing_scheduled_case(tmp_path):
    corpus = _corpus(tmp_path)
    manifest = json.loads((corpus / "manifest.json").read_text())
    manifest["cases"] = [c for c in manifest["cases"] if c["id"] != "T3b-hostile"]
    (corpus / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ev.PlanError, match="T3b-hostile"):
        ev.load_manifest(corpus)


def test_plan_rejects_a_declaration_count_the_parser_disagrees_with(tmp_path):
    manifest = ev.load_manifest(_corpus(tmp_path, declarations=50))
    with pytest.raises(ev.PlanError, match="declarations"):
        ev.build_plan(manifest, _estimates(known_y=49), "abc")


def test_plan_records_production_settings_and_hash_is_stable(tmp_path):
    manifest = ev.load_manifest(_corpus(tmp_path))
    first = ev.build_plan(manifest, _estimates(), "abc")
    second = ev.build_plan(manifest, _estimates(), "abc")
    assert first["plan_hash"] == second["plan_hash"]
    assert first["configuration"]["max_output_tokens"] == 12_288
    assert (
        ev.build_plan(manifest, _estimates(), "other")["plan_hash"]
        != first["plan_hash"]
    )
    assert [s["held_out"] for s in first["schedule"]].count(True) == 2


def test_oracle_rejects_unknown_severity(tmp_path):
    corpus = _corpus(tmp_path)
    (corpus / "bad.json").write_text(
        json.dumps(
            {"issues": [{"id": "X", "severity": "Severe", "resource_address": "a.b"}]}
        )
    )
    with pytest.raises(ev.PlanError, match="severity"):
        ev.load_oracle(corpus, {"oracle": "bad.json"})


# ----------------------------------------------------------------- journal


def test_nothing_is_recorded_before_approval(tmp_path):
    manifest = ev.load_manifest(_corpus(tmp_path))
    plan = ev.build_plan(manifest, _estimates(), "abc")
    with pytest.raises(ev.PlanError, match="not approved"):
        ev.record(ev.new_journal(plan), 1, IDS[0])


def test_approval_needs_the_current_plan_hash(tmp_path):
    manifest = ev.load_manifest(_corpus(tmp_path))
    plan = ev.build_plan(manifest, _estimates(), "abc")
    with pytest.raises(ev.PlanError):
        ev.approve(ev.new_journal(plan), plan, "0" * 64)


def test_slots_are_used_in_order_without_replacements(tmp_path):
    journal, _ = _approved_journal(tmp_path)
    with pytest.raises(ev.PlanError, match="next is 1"):
        ev.record(journal, 2, IDS[0])
    journal = ev.record(journal, 1, IDS[0])
    with pytest.raises(ev.PlanError, match="already recorded"):
        ev.record(journal, 2, IDS[0])
    for n in range(2, 13):
        journal = ev.record(journal, n, IDS[n - 1])
    with pytest.raises(ev.PlanError, match="all slots"):
        ev.record(journal, 13, IDS[12])


# -------------------------------------------------------------------- gate


def test_gate_goes_when_spend_is_known_and_within_limits(tmp_path):
    journal, _ = _approved_journal(tmp_path)
    journal = ev.record(journal, 1, IDS[0])
    result = ev.gate(journal, {IDS[0]: _run(0.2)})
    assert result["go"] is True
    assert result["next_case"] == "T1-full"
    assert result["spent_usd"] == pytest.approx(0.21)


def test_gate_waits_while_a_submitted_review_is_not_in_the_logs(tmp_path):
    journal, _ = _approved_journal(tmp_path)
    journal = ev.record(journal, 1, IDS[0])
    result = ev.gate(journal, {})
    assert result["go"] is False
    assert result["pending_slots"] == [1]
    assert result["spent_usd"] == ev.RESERVATION_USD


def test_unknown_cost_keeps_the_whole_reservation_never_zero(tmp_path):
    journal, _ = _approved_journal(tmp_path)
    journal = ev.record(journal, 1, IDS[0])
    failed = {"cost_usd": None, "outcome": "model call failed"}
    assert ev.slot_cost(failed) == (ev.RESERVATION_USD, False)
    assert ev.gate(journal, {IDS[0]: failed})["spent_usd"] == ev.RESERVATION_USD


@pytest.mark.parametrize(
    "run, reason",
    [
        (_run(0.45), "over its"),
        (_run(0.2, input_tokens=60_000), "input tokens"),
        (_run(0.2, near_max_tokens=True), "output-token limit"),
    ],
)
def test_gate_stops_the_batch_on_any_envelope_breach(tmp_path, run, reason):
    journal, _ = _approved_journal(tmp_path)
    journal = ev.record(journal, 1, IDS[0])
    result = ev.gate(journal, {IDS[0]: run})
    assert result["go"] is False
    assert any(reason in stop for stop in result["stops"])


def test_eleven_unknown_costs_still_leave_room_for_the_last_slot(tmp_path):
    journal, _ = _approved_journal(tmp_path)
    runs = {}
    for n in range(1, 12):
        journal = ev.record(journal, n, IDS[n - 1])
        runs[IDS[n - 1]] = {"cost_usd": None}  # each keeps $0.40: $4.40 spent
    result = ev.gate(journal, runs)
    assert result["go"] is True and result["spent_usd"] == pytest.approx(4.40)


def test_gate_stops_when_the_next_reservation_would_exceed_the_approval(
    tmp_path, monkeypatch
):
    journal, _ = _approved_journal(tmp_path)
    monkeypatch.setattr(ev, "BATCH_APPROVAL_USD", 0.75)
    journal = ev.record(journal, 1, IDS[0])
    result = ev.gate(journal, {IDS[0]: {"cost_usd": None}})
    assert result["go"] is False
    assert any("exceed" in stop for stop in result["stops"])


def test_gate_refuses_after_the_last_slot(tmp_path):
    journal, _ = _approved_journal(tmp_path)
    runs = {}
    for n in range(1, 13):
        journal = ev.record(journal, n, IDS[n - 1])
        runs[IDS[n - 1]] = _run(0.2)
    result = ev.gate(journal, runs)
    assert result["go"] is False
    assert "all slots used" in result["stops"]


# --------------------------------------------------------- worksheet/score


def _ledger(*findings):
    return {
        "findings": list(findings),
        "review_scope": {
            "known_y": 25,
            "x": 20,
            "sent_count": 21,
            "model_outcome": "completed",
        },
    }


def _finding(fid, text):
    return {"finding_id": fid, "type": "model", "finding": text, "evidence": []}


def test_candidates_match_whole_resource_names_only():
    findings = [
        _finding("f1", "Bucket logs has no encryption"),
        _finding("f2", "Bucket logs_archive is public"),
    ]
    assert ev.candidates("aws_s3_bucket.logs", findings) == ["f1"]


def _judged(tmp_path, caught_high="f1", verdict="valid", unsafe=False):
    journal, _ = _approved_journal(tmp_path)
    journal = ev.record(journal, 1, IDS[0])
    manifest = ev.load_manifest(tmp_path)
    cases = ev.case_by_id(manifest)
    oracles = {cid: ev.load_oracle(tmp_path, cases[cid]) for cid in set(ev.SCHEDULE)}
    ledgers = {"1": _ledger(_finding("f1", "logs bucket is unencrypted"))}
    sheet = ev.build_worksheet(journal, ledgers, oracles)
    assert sheet["issues"][0]["candidates"] == ["f1"]
    for row in sheet["issues"]:
        row["caught_by"] = caught_high if row["severity"] == "High" else "missed"
    for row in sheet["findings"]:
        row["verdict"], row["unsafe_fix"] = verdict, unsafe
    return journal, sheet, ledgers


def test_score_refuses_a_partly_judged_worksheet(tmp_path):
    journal, sheet, ledgers = _judged(tmp_path)
    sheet["findings"][0]["verdict"] = None
    with pytest.raises(ev.PlanError, match="judging incomplete"):
        ev.score(journal, sheet, ledgers, {})


def test_score_reports_recall_cost_and_counts(tmp_path):
    journal, sheet, ledgers = _judged(tmp_path)
    runs = {IDS[0]: _run(0.2, emitted=14, capped=2, accepted=11, rejected={"quote": 1})}
    report = ev.score(journal, sheet, ledgers, runs)
    slot = report["slots"][0]
    assert (slot["critical_high_caught"], slot["critical_high_total"]) == (1, 1)
    assert (slot["all_caught"], slot["all_total"]) == (1, 2)
    assert slot["model"]["emitted"] == 14 and slot["model"]["capped"] == 2
    assert report["summary"]["development"]["critical_high_recall"] == 1.0
    assert report["summary"]["held_out"]["critical_high_recall"] is None
    assert report["release_gates"] == {
        "zero_false_claims": True,
        "zero_unsafe_fixes": True,
    }
    assert report["checkpoint"]["below"] is False


def test_score_flags_misses_false_claims_and_unsafe_fixes(tmp_path):
    journal, sheet, ledgers = _judged(
        tmp_path, caught_high="missed", verdict="false_claim", unsafe=True
    )
    report = ev.score(journal, sheet, ledgers, {})
    assert report["summary"]["development"]["critical_high_recall"] == 0.0
    assert report["checkpoint"]["below"] is True
    assert report["release_gates"] == {
        "zero_false_claims": False,
        "zero_unsafe_fixes": False,
    }
    assert report["slots"][0]["cost_known"] is False
    assert report["slots"][0]["cost_usd"] == ev.RESERVATION_USD


def test_plan_hash_covers_the_manifest_itself(tmp_path):
    corpus = _corpus(tmp_path)
    first = ev.build_plan(ev.load_manifest(corpus), _estimates(), "abc")
    manifest = json.loads((corpus / "manifest.json").read_text())
    manifest["note"] = "edited after freezing"
    (corpus / "manifest.json").write_text(json.dumps(manifest))
    second = ev.build_plan(ev.load_manifest(corpus), _estimates(), "abc")
    assert first["plan_hash"] != second["plan_hash"]


def test_archive_holds_only_the_cases_terraform_files(tmp_path):
    import tarfile

    corpus = _corpus(tmp_path)
    case = ev.case_by_id(ev.load_manifest(corpus))["T3a"]
    archive = ev.build_archive(corpus, case, tmp_path / "out" / "T3a.tar.gz")
    with tarfile.open(archive) as tar:
        assert tar.getnames() == ["main.tf"]


def test_archive_refuses_a_non_terraform_file(tmp_path):
    corpus = _corpus(tmp_path)
    case = dict(ev.case_by_id(ev.load_manifest(corpus))["T3a"])
    case["terraform_files"] = ["T3a/oracle.json"]
    with pytest.raises(ev.PlanError, match="not a Terraform file"):
        ev.build_archive(corpus, case, tmp_path / "x.tar.gz")
