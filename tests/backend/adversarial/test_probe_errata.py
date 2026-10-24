from copy import deepcopy
from dataclasses import asdict
from types import SimpleNamespace

from backend.lambdas.ingest.handler import parse_terraform_files
from backend.lambdas.rule_engine.handler import run_rules
from backend.lambdas.rule_engine.resource_summary import build_resource_summary
from tests.backend.adversarial.harness import FIXTURES, judge, load_answer_key, probe
from tests.backend.adversarial.probe_errata import corrected_probe


def run(path):
    parsed = asdict(parse_terraform_files([str(FIXTURES / path / "main.tf")]))
    return SimpleNamespace(
        summary=build_resource_summary(parsed),
        findings=[f.model_dump(mode="json") for f in run_rules(parsed, "probe")],
    )


def test_f06_raw_lexical_failure_is_preserved_but_typed_contract_checks_actual_scope():
    output = run("06_backup_plan_without_protection/dangerous")
    check = next(
        check
        for case in load_answer_key()["cases"]
        for check in case["checks"]
        if check["id"] == "F06-D-04"
    )
    matched, _ = probe(check["probe"], output, {})
    assert judge(check["kind"], matched) == "fail"
    assert corrected_probe(check["id"], output)[0] is True
    wrong = deepcopy(output)
    destination = next(
        entry
        for entry in wrong.summary["resources"]
        if entry["type"] == "aws_backup_vault" and entry["name"] == "secondary"
    )
    for fact in destination["observations"]["facts"]:
        if fact["setting"] == "resource.region":
            fact["value"] = "us-west-2"
    assert corrected_probe(check["id"], wrong)[0] is False


def test_f08_affirmative_versioning_does_not_excuse_an_actual_missing_versioning_claim():
    output = run("08_seven_day_deletion_fiction/dangerous")
    check = next(
        check
        for case in load_answer_key()["cases"]
        for check in case["checks"]
        if check["id"] == "F08-D-04"
    )
    matched, _ = probe(check["probe"], output, {})
    assert judge(check["kind"], matched) == "fail"
    assert corrected_probe(check["id"], output)[0] is True
    output.findings.append(
        {"finding": "Bucket 'uploads' has no versioning", "concern": "s3_versioning"}
    )
    assert corrected_probe(check["id"], output)[0] is False
