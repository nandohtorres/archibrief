"""Assert the six oracle premises against real parsed frozen fixtures.

These do not grade generated prose, prove deployment, or close extraction gaps.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from backend.lambdas.ingest.handler import parse_terraform_files
from tests.backend.adversarial.harness import FIXTURES, load_answer_key
from tests.backend.adversarial.semantic_oracle import (
    load_semantic_oracle,
    semantic_review,
)


@pytest.fixture(scope="module")
def resources():
    result = {}
    for case in load_semantic_oracle()["cases"]:
        if case["case"] not in result:
            parsed = parse_terraform_files(
                [str(FIXTURES / case["fixture"] / "main.tf")]
            )
            result[case["case"]] = asdict(parsed)["resources"]
    return result


def test_oracle_links_frozen_cases_without_rescoring():
    oracle = load_semantic_oracle()
    key = {case["id"]: case for case in load_answer_key()["cases"]}
    assert [case["id"] for case in oracle["cases"]] == [
        "E01",
        "E02",
        "E03",
        "E04",
        "E05",
        "E06",
    ]
    for case in oracle["cases"]:
        frozen = key[case["case"]]
        assert case["fixture"] == frozen["fixture"]
        assert set(case["affected_checks"]) <= {c["id"] for c in frozen["checks"]}
        for field in (
            "owner",
            "expected_facts",
            "relationships",
            "acceptable_uncertainty",
            "forbidden_claims",
            "source",
        ):
            assert case[field], (case["id"], field)
        review = semantic_review(case["case"], oracle)
        assert review["status"] == "not_scored"
        assert case["id"] in review["criteria"]
    assert (
        semantic_review("F09-control", oracle)["status"] == "outside_supplemental_scope"
    )


def test_e01_url_auth_is_not_an_invocation_policy(resources):
    r = resources["F07-dangerous"]
    url = r["aws_lambda_function_url"]["inference_direct"]
    assert url["authorization_type"] == "NONE"
    assert url["function_name"] == "${aws_lambda_function.inference.function_name}"
    assert not r.get("aws_lambda_permission")


def test_e02_mapping_declares_invalid_timeout_relationship(resources):
    r = resources["F07-dangerous"]
    assert r["aws_sqs_queue"]["jobs"]["visibility_timeout_seconds"] == 30
    assert r["aws_lambda_function"]["inference"]["timeout"] == 300
    mapping = r["aws_lambda_event_source_mapping"]["jobs"]
    assert mapping["event_source_arn"] == "${aws_sqs_queue.jobs.arn}"
    assert mapping["function_name"] == "${aws_lambda_function.inference.arn}"


def test_e03_method_auth_does_not_establish_backend_integration(resources):
    r = resources["F07-dangerous"]
    method = r["aws_api_gateway_method"]["post_batch"]
    assert method["authorization"] == "NONE"
    assert method["resource_id"] == "${aws_api_gateway_resource.batch.id}"
    assert r["aws_api_gateway_resource"]["batch"]["path_part"] == "batch"
    assert (
        r["aws_api_gateway_authorizer"]["token"]["authorizer_uri"]
        == "${aws_lambda_function.inference.invoke_arn}"
    )
    assert not r.get("aws_api_gateway_integration")
    assert not r.get("aws_lambda_permission")


def test_e04_backup_selection_does_not_erase_native_retention(resources):
    r = resources["F06-dangerous"]
    selection = r["aws_backup_selection"]["dev_only"]
    assert selection["resources"] == ["${aws_db_instance.dev_sandbox.arn}"]
    assert selection["plan_id"] == "${aws_backup_plan.nightly.id}"
    assert r["aws_db_instance"]["prod_ledger"]["backup_retention_period"] == 7


def test_e05_replica_name_does_not_establish_replication(resources):
    r = resources["F08-dangerous"]
    assert not r.get("aws_s3_bucket_replication_configuration")
    for name in ("uploads", "uploads_replica"):
        versioning = r["aws_s3_bucket_versioning"][name]
        assert versioning["bucket"] == "${aws_s3_bucket." + name + ".id}"
        assert versioning["versioning_configuration"][0]["status"] == "Enabled"
        lifecycle = r["aws_s3_bucket_lifecycle_configuration"][name]
        assert lifecycle["bucket"] == "${aws_s3_bucket." + name + ".id}"
        rule = lifecycle["rule"][0]
        assert rule["expiration"][0]["days"] == 7
        assert "noncurrent_version_expiration" not in rule


def test_e06_copy_has_source_retention_without_explicit_override(resources):
    r = resources["F06-dangerous"]
    rules = r["aws_backup_plan"]["nightly"]["rule"]
    assert len(rules) == 11
    copies = [rule for rule in rules if rule.get("copy_action")]
    assert len(copies) == 1
    rule = copies[0]
    assert rule["rule_name"] == "rule_11"
    assert rule["lifecycle"][0]["delete_after"] == 1
    copy = rule["copy_action"][0]
    assert copy["destination_vault_arn"] == "${aws_backup_vault.secondary.arn}"
    assert "lifecycle" not in copy
    assert "provider" not in r["aws_backup_vault"]["primary"]
    assert "provider" not in r["aws_backup_vault"]["secondary"]


def test_exports_preserve_raw_failures_and_leave_semantics_unscored(
    tmp_path, monkeypatch
):
    from tests.backend.adversarial import run_adversarial as runner

    frozen = load_answer_key()
    key = {
        **frozen,
        "cases": [c for c in frozen["cases"] if c["id"] == "F07-dangerous"],
    }
    monkeypatch.setattr(runner, "load_answer_key", lambda: key)
    monkeypatch.setattr(runner, "trivy_path", lambda: None)
    monkeypatch.setattr(runner, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(runner, "MODEL_INPUTS", tmp_path / "inputs")
    monkeypatch.setattr(runner.tempfile, "mkdtemp", lambda **kw: str(tmp_path / "work"))
    # Corrected criteria alone must never turn missing detections into passes.
    monkeypatch.setattr(runner, "probe", lambda *a: (False, "missing"))
    monkeypatch.setattr(
        runner, "run_fixture", lambda *a: SimpleNamespace(findings=[], summary={})
    )
    runner.main()
    rows = json.loads((tmp_path / "results" / "results.json").read_text())
    detections = [row for row in rows if row["kind"] == "must_detect"]
    assert detections
    assert all(row["verdict"].startswith("fail") for row in detections)
    assert all(row["adjudicated"].startswith("fail") for row in detections)
    assert all(row["semantic_review"]["status"] == "not_scored" for row in rows)
    payload = json.loads((tmp_path / "inputs" / "F07-dangerous.json").read_text())
    assert payload["semantic_review"]["criteria"] == ["E01", "E02", "E03"]
    assert [c["id"] for c in payload["supplemental_criteria"]] == ["E01", "E02", "E03"]
    table = (tmp_path / "results" / "results_table.md").read_text()
    assert "no revised semantic pass rate has been measured" in table
    assert "semantic-oracle@2026-10-23" in table
