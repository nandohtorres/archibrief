"""Archive-root inventory and every ingest fixture in the slim P0 contract."""

import json
from dataclasses import asdict

import pytest

from backend.lambdas.ingest import handler as ingest
from backend.lambdas.rule_engine.handler import handler as rule_engine
from tests.backend.lambdas.ingest.test_handler import (
    _FakeGuardrailsClient,
    _make_archive,
)
from tests.backend.p0_scope_fixtures import scope_api


def _run(tmp_path, files, *, storage=None):
    archive = tmp_path / "input.tar"
    _make_archive(str(archive), {name: text.encode() for name, text in files.items()})
    guard = _FakeGuardrailsClient(allow=True, calls=[])
    event = {
        "archive_path": str(archive),
        "dest_dir": str(tmp_path / "extracted"),
        "review_id": "p0-fixture",
        "workload_brief": "A small workload",
    }
    if storage is not None:
        event["report_bucket"] = "reports"
    result = ingest.handler(event, None, guardrails_client=guard, s3_client=storage)
    return result, guard


def _completed(parsed):
    response = rule_engine({"review_id": "p0-fixture", "parsed": parsed}, None)
    return scope_api().finalize_scope(
        parsed["review_scope"], response["summary_members"], "completed"
    )


@pytest.mark.parametrize(
    "n", [0, 1, 49, 50, 51], ids=["F00", "F01", "F49", "F50", "F51"]
)
def test_f00_f01_f49_f50_f51_root_counts_without_enforcing_fifty(tmp_path, n):
    source = 'provider "aws" { region = "us-east-1" }\n'
    source += "\n".join(f'resource "aws_s3_bucket" "b{i}" {{}}' for i in range(n))
    result, guard = _run(tmp_path, {"main.tf": source})
    assert result["status"] == "parsed"
    assert len(guard.calls) == 1
    pending = result["review_scope"]
    assert pending["status"] == "pending"
    assert pending["known_y"] == n
    assert pending["count_complete"] is True
    final = _completed(result)
    assert final["x"] == final["known_y"] == n
    assert final["sent_count"] == n
    assert sum(final["categories"].values()) == n


def test_f_reuse_captures_keys_after_collision_suffix_and_call_addresses(tmp_path):
    result, _ = _run(
        tmp_path,
        {
            "main.tf": 'module "web" { source = "./unit" }\nmodule "jobs" { source = "./unit" }',
            "unit/main.tf": 'resource "aws_s3_bucket" "main" {}',
        },
    )
    pending = result["review_scope"]
    declarations = pending["declarations"]
    assert pending["known_y"] == 2
    assert {d["address"] for d in declarations} == {
        "module.web.aws_s3_bucket.main",
        "module.jobs.aws_s3_bucket.main",
    }
    assert {d["parsed_key"] for d in declarations} == set(
        result["resources"]["aws_s3_bucket"]
    )
    assert {d["parsed_key"] for d in declarations} == {"unit/main", "jobs_1/unit/main"}
    assert _completed(result)["x"] == 2


@pytest.mark.parametrize(
    "duplicate,detail",
    [
        ('resource "aws_s3_bucket" "PRIVATE_NAME" {}', "duplicate_resource"),
        ('module "PRIVATE_NAME" { source = "./unit" }', "duplicate_module_call"),
    ],
    ids=["F-dup", "F-dup-call"],
)
def test_f_dup_and_f_dup_call_rejected_before_guardrails(tmp_path, duplicate, detail):
    result, guard = _run(
        tmp_path,
        {
            "PRIVATE_A.tf": duplicate,
            "PRIVATE_B.tf": duplicate,
            "unit/main.tf": 'resource "aws_s3_bucket" "child" {}',
        },
    )
    assert result["status"] == "rejected"
    assert result["code"] == "malformed_configuration"
    assert result["detail"] == detail
    assert guard.calls == []
    assert isinstance(result["reason"], str) and result["reason"]
    for private in (
        "PRIVATE_NAME",
        "PRIVATE_A.tf",
        "PRIVATE_B.tf",
        str(tmp_path),
        duplicate,
    ):
        assert private not in result["reason"]


def test_f_dup_uncalled_does_not_reject_or_count_uncalled_directory(tmp_path):
    duplicate = 'resource "aws_s3_bucket" "duplicate" {}'
    result, guard = _run(
        tmp_path,
        {
            "main.tf": 'resource "aws_s3_bucket" "root" {}',
            "unused/a.tf": duplicate,
            "unused/b.tf": duplicate,
        },
    )
    assert result["status"] == "parsed"
    assert len(guard.calls) == 1
    assert result["review_scope"]["known_y"] == 1
    assert result["review_scope"]["module_gaps"] == []


def test_reached_child_duplicates_are_rejected(tmp_path):
    duplicate = 'resource "aws_s3_bucket" "duplicate" {}'
    result, guard = _run(
        tmp_path,
        {
            "main.tf": 'module "child" { source = "./unit" }',
            "unit/a.tf": duplicate,
            "unit/b.tf": duplicate,
        },
    )
    assert result["status"] == "rejected"
    assert result["detail"] == "duplicate_resource"
    assert guard.calls == []


def test_f_zero_res_counts_once_as_zero_copy(tmp_path):
    result, _ = _run(
        tmp_path, {"main.tf": 'resource "aws_s3_bucket" "off" { count = 0 }'}
    )
    assert result["review_scope"]["known_y"] == 1
    final = _completed(result)
    assert final["x"] == 0
    assert final["declarations"][0]["instances"] == 0
    assert final["declarations"][0]["category"] == "zero_copy"
    assert final["module_gaps"] == []


@pytest.mark.parametrize("disabled", ["count = 0", "for_each = {}", "for_each = []"])
def test_f_zero_mod_contributes_no_declaration_or_gap(tmp_path, disabled):
    result, _ = _run(
        tmp_path,
        {
            "main.tf": f'module "off" {{\nsource = "./unit"\n{disabled}\n}}',
            "unit/main.tf": 'resource "aws_s3_bucket" "unused" {}',
        },
    )
    assert result["review_scope"]["known_y"] == 0
    assert result["review_scope"]["module_gaps"] == []


def test_f_unknown_resource_instances_are_null_but_reviewed(tmp_path):
    result, _ = _run(
        tmp_path,
        {
            "main.tf": 'variable "n" {}\nresource "aws_s3_bucket" "main" { count = var.n }'
        },
    )
    final = _completed(result)
    assert final["known_y"] == final["x"] == 1
    assert final["declarations"][0]["instances"] is None
    assert final["declarations"][0]["category"] == "reviewed"


@pytest.mark.parametrize(
    "repetition,instances",
    [
        ("", 1),
        ("count = 7", 7),
        ("for_each = { a = 1, b = 2 }", 2),
        ("count = 1001", None),
    ],
)
def test_repetition_counts_declaration_once(tmp_path, repetition, instances):
    result, _ = _run(
        tmp_path, {"main.tf": f'resource "aws_s3_bucket" "main" {{ {repetition} }}'}
    )
    assert result["review_scope"]["known_y"] == 1
    assert result["review_scope"]["declarations"][0]["instances"] == instances


def test_f_remote_counts_only_known_bucket_and_records_module_gap(tmp_path):
    result, _ = _run(
        tmp_path,
        {
            "main.tf": 'resource "aws_s3_bucket" "main" {}\nmodule "vpc" { source = "terraform-aws-modules/vpc/aws" }'
        },
    )
    final = _completed(result)
    assert final["known_y"] == final["x"] == 1
    assert final["module_gaps"] == [
        {"address": "module.vpc", "reasons": ["remote_source"]}
    ]


def test_f_nonaws_is_unsupported_but_still_a_summary_member(tmp_path):
    result, _ = _run(
        tmp_path,
        {
            "main.tf": 'resource "aws_s3_bucket" "main" {}\nresource "random_id" "id" { byte_length = 4 }'
        },
    )
    final = _completed(result)
    assert (final["known_y"], final["x"], final["sent_count"]) == (2, 1, 2)
    assert final["categories"] == {
        "reviewed": 1,
        "zero_copy": 0,
        "unsupported": 1,
        "other": 0,
    }


def test_f_filtered_counts_valid_header_even_if_summary_rejects_type(tmp_path):
    result, _ = _run(tmp_path, {"main.tf": 'resource "aws_Custom" "main" {}'})
    final = _completed(result)
    assert final["known_y"] == 1
    assert final["declarations"][0]["reason"] == "summary_filtered"


def test_f_clone_res_inventories_both_headers_before_body_loss(tmp_path, monkeypatch):
    # ASSUMPTION: see Q2; public budget constant is a fixture control.
    monkeypatch.setattr(ingest, "MAX_MODULE_EXPANSION_BYTES", 128)
    result, _ = _run(
        tmp_path,
        {
            "main.tf": 'resource "aws_s3_bucket" "first" {}\nresource "aws_s3_bucket" "second" { bucket = "'
            + "x" * 1024
            + '" }'
        },
    )
    assert set(result["resources"]["aws_s3_bucket"]) == {"first"}
    pending = result["review_scope"]
    assert pending["known_y"] == 2
    assert pending["count_complete"] is True
    assert pending["module_gaps"] == []
    items = {d["address"]: d for d in _completed(result)["declarations"]}
    assert items["aws_s3_bucket.first"]["category"] == "reviewed"
    assert items["aws_s3_bucket.second"]["retained"] is False
    assert items["aws_s3_bucket.second"]["reason"] == "not_retained"


@pytest.mark.parametrize(
    "early_block",
    [
        'variable "large" { default = "%s" }',
        'locals { large = "%s" }',
        'provider "aws" { region = "%s" }',
    ],
)
def test_inventory_precedes_variable_local_and_provider_cloning(
    tmp_path, monkeypatch, early_block
):
    # ASSUMPTION: see Q2.
    monkeypatch.setattr(ingest, "MAX_MODULE_EXPANSION_BYTES", 128)
    source = early_block % ("x" * 1024) + '\nresource "aws_s3_bucket" "main" {}'
    result, _ = _run(tmp_path, {"main.tf": source})
    pending = result["review_scope"]
    assert pending["known_y"] == 1
    assert pending["declarations"][0]["retained"] is False
    assert pending["module_gaps"] == []


@pytest.mark.parametrize(
    "disabled",
    [None, "count = 0", "for_each = {}"],
    ids=["F-clone-child", "F-stop-disabled-count", "F-stop-disabled-each"],
)
def test_f_clone_child_and_f_stop_disabled_account_for_unentered_calls(
    tmp_path, monkeypatch, disabled
):
    # ASSUMPTION: see Q2.
    monkeypatch.setattr(ingest, "MAX_MODULE_EXPANSION_BYTES", 128)
    source = (
        'locals { large = "'
        + "x" * 1024
        + '" }\nmodule "enabled" { source = "./unit" }'
    )
    if disabled:
        source += f'\nmodule "disabled" {{\nsource = "./unit"\n{disabled}\n}}'
    result, _ = _run(
        tmp_path,
        {"main.tf": source, "unit/main.tf": 'resource "aws_s3_bucket" "child" {}'},
    )
    scope = result["review_scope"]
    assert scope["known_y"] == 0
    assert scope["module_gaps"] == [
        {"address": "module.enabled", "reasons": ["expansion_limit"]}
    ]


def test_f_root_nested_only_archive_preserves_legacy_parse_but_has_unknown_count(
    tmp_path,
):
    result, _ = _run(tmp_path, {"unit/main.tf": 'resource "aws_s3_bucket" "main" {}'})
    assert result["status"] == "parsed"
    assert result["resource_count"] == 1
    assert result["review_scope"]["state"] == "unknown_root"
    assert result["review_scope"]["known_y"] is None
    assert result["review_scope"]["declarations"] == []


@pytest.mark.parametrize(
    "location,reached",
    [
        ("extra.tf.json", True),
        ("unit/extra.tf.json", True),
        ("unused/extra.tf.json", False),
    ],
)
def test_f_json_discloses_skipped_json_only_in_reached_sources(
    tmp_path, location, reached
):
    result, _ = _run(
        tmp_path,
        {
            "main.tf": 'resource "aws_s3_bucket" "main" {}\nmodule "unit" { source = "./unit" }',
            "unit/main.tf": 'provider "aws" {}',
            location: '{"resource": {}}',
        },
    )
    scope = result["review_scope"]
    assert ("skipped_tf_json" in scope["warnings"]) is reached
    assert scope["count_complete"] is (not reached)


def test_json_only_archive_keeps_rejection(tmp_path):
    result, guard = _run(tmp_path, {"main.tf.json": '{"resource": {}}'})
    assert result["status"] == "rejected"
    assert "code" not in result
    assert guard.calls == []


@pytest.mark.parametrize(
    "call,reason",
    [
        ('source = "./missing"', "source_missing"),
        ('source = "./"', "cycle"),
        ('source = "./unit"\ncount = 2', "count_not_singleton"),
        ('source = "./unit"\nfor_each = { a = 1 }', "for_each_unsupported"),
        ('source = "../outside"', "source_outside_archive"),
        ("source = var.source", "source_unresolved"),
        ('source = "./unit"\ncount = var.n', "count_unresolved"),
    ],
)
def test_f_gaps_each_unreadable_call_has_exact_reason(tmp_path, call, reason):
    result, _ = _run(
        tmp_path,
        {
            "main.tf": f'variable "n" {{}}\nvariable "source" {{}}\nmodule "child" {{\n{call}\n}}',
            "unit/main.tf": 'resource "aws_s3_bucket" "main" {}',
        },
    )
    assert result["review_scope"]["module_gaps"] == [
        {"address": "module.child", "reasons": [reason]}
    ]
    assert result["review_scope"]["known_y"] == 0


def test_unknown_module_inputs_and_provider_mapping_are_not_unreadable_modules(
    tmp_path,
):
    result, _ = _run(
        tmp_path,
        {
            "main.tf": 'variable "unset" {}\nmodule "child" {\nsource = "./unit"\nvalue = var.unset\n}',
            "unit/main.tf": 'variable "value" {}\nresource "aws_s3_bucket" "main" { bucket = var.value }',
        },
    )
    assert result["review_scope"]["known_y"] == 1
    assert result["review_scope"]["module_gaps"] == []


@pytest.mark.parametrize("size,complete", [(1000, True), (1001, False)])
def test_inventory_bound_records_lower_bound_without_rejecting(
    tmp_path, size, complete
):
    source = "\n".join(f'resource "aws_s3_bucket" "b{i}" {{}}' for i in range(size))
    result, _ = _run(tmp_path, {"main.tf": source})
    scope = result["review_scope"]
    assert result["status"] == "parsed"
    assert scope["known_y"] == len(scope["declarations"]) == 1000
    assert scope["count_complete"] is complete


@pytest.mark.parametrize("size,complete", [(100, True), (101, False)])
def test_gap_bound_records_lower_bound(tmp_path, size, complete):
    source = "\n".join(
        f'module "m{i}" {{ source = "registry.example/x/y" }}' for i in range(size)
    )
    result, _ = _run(tmp_path, {"main.tf": source})
    scope = result["review_scope"]
    assert len(scope["module_gaps"]) == 100
    assert scope["gaps_complete"] is complete


def test_explicit_root_preserves_legacy_fields_and_legacy_call_has_unknown_scope(
    tmp_path,
):
    source = tmp_path / "main.tf"
    source.write_text('resource "aws_s3_bucket" "main" {}', encoding="utf-8")
    legacy = asdict(ingest.parse_terraform_files([str(source)]))
    assert legacy["review_scope"]["state"] == "unknown_root"
    explicit = asdict(
        ingest.parse_terraform_files([str(source)], archive_root=str(tmp_path))
    )
    assert explicit.pop("review_scope")["known_y"] == 1
    legacy.pop("review_scope")
    assert explicit == legacy


def test_extract_reports_skipped_member_names_without_changing_returned_files(tmp_path):
    archive = tmp_path / "input.tar"
    _make_archive(
        str(archive),
        {
            "main.tf": b'provider "aws" {}',
            "unit/extra.tf.json": b"{}",
            "terraform.tfvars.json": b"{}",
        },
    )
    skipped = []
    paths = ingest.extract_archive(
        str(archive), str(tmp_path / "out"), skipped_tf_json=skipped
    )
    assert skipped == ["unit/extra.tf.json"]
    assert {p.replace("\\", "/").split("/")[-1] for p in paths} == {
        "main.tf",
        "terraform.tfvars.json",
    }


def test_pending_scope_is_written_once_with_the_parsed_payload(tmp_path):
    writes = []

    class Storage:
        def put_object(self, key, body):
            writes.append((key, json.loads(body)))

    result, _ = _run(
        tmp_path, {"main.tf": 'resource "aws_s3_bucket" "main" {}'}, storage=Storage()
    )
    assert result["parsed_s3_key"] == "parsed/p0-fixture.json"
    assert len(writes) == 1
    assert writes[0][0] == result["parsed_s3_key"]
    record = writes[0][1]["review_scope"]
    assert record["status"] == "pending"
    assert record["known_y"] == 1
    assert scope_api().validate_scope(record) == []


def test_nonresource_blocks_are_not_declarations(tmp_path):
    result, _ = _run(
        tmp_path,
        {
            "main.tf": """
provider "aws" { region = "us-east-1" }
variable "label" { default = "test" }
locals { name = var.label }
data "aws_caller_identity" "current" {}
output "label" { value = local.name }
"""
        },
    )
    assert result["review_scope"]["known_y"] == 0
    assert result["review_scope"]["declarations"] == []


def test_depth_stop_records_unread_module_as_gap(tmp_path):
    files = {"main.tf": 'module "m1" { source = "./m1" }'}
    for i in range(1, 10):
        files[f"m{i}/main.tf"] = f'module "m{i + 1}" {{ source = "../m{i + 1}" }}'
    files["m10/main.tf"] = 'resource "aws_s3_bucket" "deep" {}'
    result, _ = _run(tmp_path, files)
    gaps = result["review_scope"]["module_gaps"]
    assert len(gaps) == 1
    assert gaps[0]["reasons"] == ["depth_limit"]
    assert gaps[0]["address"].startswith("module.m1.module.m2.")


def test_module_expansion_limit_records_each_unentered_call(tmp_path):
    result, _ = _run(
        tmp_path,
        {
            "main.tf": "\n".join(
                f'module "m{i}" {{ source = "./unit" }}' for i in range(80)
            ),
            "unit/main.tf": 'resource "aws_s3_bucket" "main" {}',
        },
    )
    scope = result["review_scope"]
    assert scope["known_y"] + len(scope["module_gaps"]) == 80
    assert scope["module_gaps"]
    assert all(gap["reasons"] == ["expansion_limit"] for gap in scope["module_gaps"])
    assert len({gap["address"] for gap in scope["module_gaps"]}) == len(
        scope["module_gaps"]
    )


def test_parse_explicit_skipped_json_metadata_marks_count_incomplete(tmp_path):
    source = tmp_path / "main.tf"
    source.write_text('resource "aws_s3_bucket" "main" {}', encoding="utf-8")
    parsed = ingest.parse_terraform_files(
        [str(source)],
        archive_root=str(tmp_path),
        skipped_tf_json=["extra.tf.json"],
    )
    assert parsed.review_scope["known_y"] == 1
    assert parsed.review_scope["count_complete"] is False
    assert "skipped_tf_json" in parsed.review_scope["warnings"]
