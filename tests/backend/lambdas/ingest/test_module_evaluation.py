from dataclasses import asdict

from backend.lambdas.ingest.handler import handler, parse_terraform_files
from backend.lambdas.rule_engine.handler import run_rules
from backend.lambdas.rule_engine.resource_summary import build_resource_summary


def parse(tmp_path, files):
    paths = []
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        paths.append(str(path))
    return asdict(parse_terraform_files(paths))


def test_only_called_nonzero_modules_are_evaluated_with_separate_inputs(tmp_path):
    parsed = parse(tmp_path, {
        "main.tf": '''
module "off" { source = "./modules/off" count = 0 }
module "safe" { source = "./modules/edge" open = false }
module "unsafe" { source = "./modules/edge" open = true }
''',
        "modules/edge/main.tf": '''
variable "open" { default = false }
resource "aws_db_instance" "db" { publicly_accessible = var.open }
''',
        "modules/off/main.tf": 'resource "aws_s3_bucket" "off" {}',
        "modules/unused/main.tf": 'resource "aws_s3_bucket" "never" {}',
    })
    assert "aws_s3_bucket" not in parsed["resources"]
    dbs = build_resource_summary(parsed)["resources"]
    assert len(dbs) == 2
    assert sorted(e["settings"]["publicly_accessible"] for e in dbs) == [False, True]
    assert len({e["name"] for e in dbs}) == 2


def test_unknown_module_input_does_not_fall_back_to_child_default(tmp_path):
    parsed = parse(tmp_path, {
        "main.tf": 'variable "open" {}\nmodule "edge" { source = "./edge" open = var.open }',
        "edge/main.tf": 'variable "open" { default = false }\nresource "aws_db_instance" "db" { publicly_accessible = var.open }',
    })
    (db,) = build_resource_summary(parsed)["resources"]
    assert db["settings"]["publicly_accessible"] == "unknown"
    assert any("input" in gap.lower() for gap in parsed["not_observable"])


def test_nested_local_module_binds_parent_input_and_unresolved_calls_are_disclosed(tmp_path):
    parsed = parse(tmp_path, {
        "main.tf": '''
module "parent" { source = "./parent" open = true }
module "remote" { source = "registry.example/team/network/aws" }
module "escape" { source = "../../outside" }
module "missing" { source = "./absent" }
''',
        "parent/main.tf": '''
variable "open" {}
module "child" { source = "../child" open = var.open }
''',
        "child/main.tf": 'variable "open" {}\nresource "aws_db_instance" "db" { publicly_accessible = var.open }',
    })
    (db,) = build_resource_summary(parsed)["resources"]
    assert db["settings"]["publicly_accessible"] is True
    gaps = " ".join(parsed["not_observable"])
    assert all(name in gaps for name in ("remote", "escape", "missing"))
    assert "registry.example" not in gaps
    assert any(f.type.value == "not-observable" and "module" in f.finding.lower() for f in run_rules(parsed, "modules"))
    assert "not_observable" in build_resource_summary(parsed)


def test_scanner_cannot_reintroduce_an_uncalled_or_zero_module_resource(tmp_path):
    parsed = parse(tmp_path, {
        "main.tf": 'module "off" { source = "./off" count = 0 }',
        "off/main.tf": 'resource "aws_db_instance" "never" { publicly_accessible = true }',
    })
    scanner = {"status": "ok", "results": [{
        "check_id": "AWS-0180", "resource_type": "aws_db_instance", "resource_key": "off/never",
        "file": "off/main.tf", "start_line": 1,
    }]}
    findings = run_rules(parsed, "modules", scanner)
    assert not any("'off/never'" in f.finding for f in findings)


def test_recursive_and_unknown_cardinality_modules_are_bounded_and_disclosed(tmp_path):
    parsed = parse(tmp_path, {
        "main.tf": '''
variable "copies" {}
module "unknown" { source = "./child" count = var.copies }
module "recursive" { source = "./child" }
''',
        "child/main.tf": 'module "again" { source = "../child" }',
    })
    gaps = " ".join(parsed["not_observable"]).lower()
    assert "count" in gaps and "cycl" in gaps


def test_module_expansion_has_a_global_budget_and_discloses_independent_slices(tmp_path):
    parsed = parse(tmp_path / "budget", {
        "main.tf": "\n".join(f'module "call{i}" {{ source = "./child" }}' for i in range(70)),
        "child/main.tf": 'resource "aws_s3_bucket" "bucket" {}',
    })
    assert len(parsed["resources"]["aws_s3_bucket"]) <= 64
    assert any("budget" in gap for gap in parsed["not_observable"])
    slices = parse(tmp_path / "slices", {
        "a/main.tf": 'resource "aws_s3_bucket" "a" {}',
        "b/main.tf": 'resource "aws_s3_bucket" "b" {}',
    })
    assert any("independent static slices" in gap for gap in slices["not_observable"])


def test_module_input_cannot_resolve_against_an_unrelated_child_default(tmp_path):
    parsed = parse(tmp_path, {
        "main.tf": 'variable "external" {}\nmodule "child" { source = "./child" open = var.external }',
        "child/main.tf": '''
variable "open" { default = false }
variable "external" { default = false }
resource "aws_db_instance" "db" { publicly_accessible = var.open }
''',
    })
    assert build_resource_summary(parsed)["resources"][0]["settings"]["publicly_accessible"] == "unknown"


def test_unknown_module_provider_mapping_cannot_prove_imds_account_scope(tmp_path):
    parsed = parse(tmp_path, {
        "main.tf": 'module "child" { source = "./child" providers = { aws = aws.west } }',
        "child/main.tf": '''
resource "aws_ec2_instance_metadata_defaults" "defaults" { http_tokens = "required" }
resource "aws_instance" "worker" {}
''',
    })
    assert any(f.concern == "ec2_imdsv2" for f in run_rules(parsed, "provider"))


def test_unknown_module_scanner_address_cannot_reintroduce_a_disabled_call(tmp_path):
    parsed = parse(tmp_path, {
        "main.tf": 'module "off" { source = "./off" count = 0 }',
        "off/main.tf": 'resource "aws_db_instance" "db" { publicly_accessible = true }',
    })
    findings = run_rules(parsed, "modules", {"status": "ok", "results": [{
        "check_id": "AWS-0180", "scope": "module", "resource_key": "off", "file": "main.tf",
    }]})
    assert not any("'off'" in f.finding for f in findings)
    assert any(f.type.value == "not-observable" and "scanner" in f.finding for f in findings)


def test_ingest_payload_keeps_module_scope_for_downstream_scanner_filtering(tmp_path):
    import io
    import tarfile

    archive = tmp_path / "input.tar"
    text = b'resource "aws_kms_key" "root" {}\nmodule "remote" { source = "vendor/network/aws" }'
    with tarfile.open(archive, "w") as tar:
        info = tarfile.TarInfo("main.tf")
        info.size = len(text)
        tar.addfile(info, io.BytesIO(text))
    result = handler({"archive_path": str(archive), "workload_brief": "test"}, None)
    assert result["module_evaluation"] == "calls"


def test_child_scanner_callsite_cannot_accuse_a_same_named_private_root_database(tmp_path):
    from backend.lambdas.scan.handler import trusted_results

    parsed = parse(tmp_path, {
        "main.tf": '''
resource "aws_db_instance" "orders" { publicly_accessible = false }
module "child" { source = "./child" }
''',
        "child/main.tf": 'resource "aws_db_instance" "orders" { publicly_accessible = true }',
    })
    results = trusted_results({"Results": [{"Target": "main.tf", "Misconfigurations": [{
        "ID": "AWS-0180", "Status": "FAIL", "CauseMetadata": {
            "Resource": "module.child.aws_db_instance.orders", "StartLine": 3,
        },
    }]}]}, str(tmp_path), [str(tmp_path / "main.tf"), str(tmp_path / "child/main.tf")])
    findings = run_rules(parsed, "callsite", {"status": "ok", "results": results})
    public = [f for f in findings if f.concern == "rds_public"]
    assert public
    assert all("child/orders" in f.finding for f in public)


def test_generated_module_scope_cannot_overwrite_another_physical_module_path(tmp_path):
    parsed = parse(tmp_path, {
        "main.tf": '''
module "a" { source = "./shared" open = true }
module "z" { source = "./b/shared" open = true }
module "b" { source = "./shared" open = false }
''',
        "shared/main.tf": 'variable "open" {}\nresource "aws_db_instance" "db" { publicly_accessible = var.open }',
        "b/shared/main.tf": 'variable "open" {}\nresource "aws_db_instance" "db" { publicly_accessible = var.open }',
    })
    dbs = build_resource_summary(parsed)["resources"]
    assert len(dbs) == 3
    assert sorted(e["settings"]["publicly_accessible"] for e in dbs) == [False, True, True]


def test_successful_scanner_without_child_results_cannot_suppress_module_own_rules(tmp_path):
    parsed = parse(tmp_path, {
        "main.tf": 'module "child" { source = "./child" }',
        "child/main.tf": 'resource "aws_db_instance" "db" { publicly_accessible = true }',
    })
    findings = run_rules(parsed, "empty-child", {"status": "ok", "results": []})
    assert any(f.concern == "rds_public" and "child/db" in f.finding for f in findings)


def test_module_expansion_has_an_aggregate_byte_budget(tmp_path, monkeypatch):
    from backend.lambdas.ingest import handler as ingest

    monkeypatch.setattr(ingest, "MAX_MODULE_EXPANSION_BYTES", 1000, raising=False)
    parsed = parse(tmp_path, {
        "main.tf": '\n'.join(f'module "c{i}" {{ source = "./child" }}' for i in range(20)),
        "child/main.tf": 'resource "aws_s3_bucket" "large" { bucket = "' + 'a' * 400 + '" }',
    })
    assert len(parsed["resources"]["aws_s3_bucket"]) <= 2
    assert any("byte budget" in gap for gap in parsed["not_observable"])


def test_bound_module_values_also_consume_the_expansion_byte_budget(tmp_path, monkeypatch):
    from backend.lambdas.ingest import handler as ingest

    monkeypatch.setattr(ingest, "MAX_MODULE_EXPANSION_BYTES", 1000)
    parsed = parse(tmp_path, {
        "main.tf": 'variable "payload" { default = [' + ','.join(str(i) for i in range(100)) + '] }\n' +
        '\n'.join(f'module "c{i}" {{ source = "./child" payload = var.payload }}' for i in range(5)),
        "child/main.tf": 'variable "payload" {}',
    })
    values = [v for k, v in parsed["variables"].items() if '/' in k and 'value' in v]
    assert len(values) < 5
    assert any("byte budget" in gap for gap in parsed["not_observable"])
