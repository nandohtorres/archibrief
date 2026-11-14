"""Read-only, offline P1 corpus checks. Run with the repo's backend dependencies.

This checks authored evidence and ingest counts, not model accuracy or deployment.
It never invokes the ingest Lambda handler, scanners, SDK clients or Terraform.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
sys.path.insert(0, str(REPO))
os.environ["AWS_EC2_METADATA_DISABLED"] = "true"


def forbid_network(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto", "subprocess.Popen", "os.system"}:
        raise RuntimeError(f"Offline corpus validation forbids {event}")


sys.addaudithook(forbid_network)

import hcl2  # noqa: E402
from hcl2.utils import SerializationOptions  # noqa: E402

from backend.lambdas.ingest.handler import parse_terraform_files  # noqa: E402
from backend.shared.review_scope import validate_scope  # noqa: E402

OPTIONS = SerializationOptions(strip_string_quotes=True, with_comments=False)
EXPECTED = {"T1-small": 25, "T1-full": 50, "T2-small": 25, "T2-full": 50, "T3a": 50, "T3b": 50}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_literal(value, variables):
    if isinstance(value, str) and value.startswith("${"):
        match = re.fullmatch(r"\$\{var\.([A-Za-z0-9_]+)\}", value)
        require(bool(match), f"Independent inventory cannot resolve {value}")
        return variables[match[1]]
    return value


def independent_inventory(root):
    """Walk local calls from the real root; never use ingest's count or helpers.

    Deliberately limited to this corpus's literal/single-variable static subset.
    Fails on unsupported repetition instead of pretending to evaluate Terraform.
    """
    declarations, gaps, disabled, sources = [], [], [], {}

    def visit(directory, prefix="", variables=None, ancestors=()):
        require(directory not in ancestors, "Module cycle in authored corpus")
        variables = dict(variables or {})
        docs = []
        for file in sorted(directory.glob("*.tf")):
            with file.open(encoding="utf-8") as stream:
                docs.append((file, hcl2.load(stream, serialization_options=OPTIONS)))
        for _, doc in docs:
            for entry in doc.get("variable", []):
                for name, body in entry.items():
                    if name not in variables and "default" in body:
                        variables[name] = body["default"]
        call_names = set()
        for file, doc in docs:
            for entry in doc.get("resource", []):
                for kind, names in entry.items():
                    for name, body in names.items():
                        address = prefix + kind + "." + name
                        require(address not in sources, "Duplicate " + address)
                        text = file.read_text(encoding="utf-8").splitlines()
                        header = f'resource "{kind}" "{name}" {{'
                        line = next(i+1 for i, t in enumerate(text) if t.strip() == header)
                        instances = 1
                        if "count" in body:
                            instances = resolve_literal(body["count"], variables)
                            require(type(instances) is int and instances >= 0, "Unsupported resource count")
                        elif "for_each" in body:
                            collection = resolve_literal(body["for_each"], variables)
                            require(isinstance(collection, (dict, list)), "Unsupported resource for_each")
                            instances = len(collection)
                        item = {"address": address, "type": kind, "file": file.relative_to(root).as_posix(),
                                "line": line, "instances": instances}
                        declarations.append(item)
                        sources[address] = item
            for entry in doc.get("module", []):
                for name, body in entry.items():
                    address = prefix + "module." + name
                    require(name not in call_names, "Duplicate module " + address)
                    call_names.add(name)
                    copies = resolve_literal(body.get("count", 1), variables)
                    if "for_each" in body:
                        each = resolve_literal(body["for_each"], variables)
                        require(each == {} or each == [], "Unsupported module for_each")
                        copies = 0
                    if copies == 0:
                        disabled.append(address)
                        continue
                    require(copies == 1, "Unsupported module repetition")
                    source = body["source"]
                    if not source.startswith(("./", "../")):
                        gaps.append({"address": address, "reasons": ["remote_source"]})
                        continue
                    target = (directory/source).resolve()
                    require(target.is_relative_to(root), "Module leaves fixture")
                    require(target.is_dir(), "Missing local module")
                    bindings = {k: resolve_literal(v, variables) for k, v in body.items()
                                if k not in {"source", "count", "for_each", "providers", "version", "depends_on"}}
                    visit(target, address+".", bindings, ancestors+(directory,))

    visit(root)
    return {"declarations": sorted(declarations, key=lambda d: d["address"]),
            "module_gaps": sorted(gaps, key=lambda d: d["address"]),
            "disabled_module_calls": sorted(disabled)}


def evidence_check(root, evidence):
    file = (root/evidence["file"]).resolve()
    require(file.is_relative_to(root), "Evidence leaves fixture")
    lines = file.read_text(encoding="utf-8").splitlines()
    line = evidence["line"]
    require(type(line) is int and 1 <= line <= len(lines), "Invalid evidence line")
    require(lines[line-1].strip() == evidence["quote"], f"Stale evidence: {file}:{line}")
    require(evidence["location"] == f"{evidence['file']}:{line}", "Inconsistent evidence location")


def inspect_architecture(name, check_saved_inventory=True):
    root = ROOT/name
    independent = independent_inventory(root)
    source_addresses = {d["address"] for d in independent["declarations"]}
    require(len(source_addresses) == EXPECTED[name], f"Independent count mismatch: {name}")
    paths = [str(p) for p in sorted(root.rglob("*.tf"))]
    parsed = parse_terraform_files(paths, archive_root=str(root))
    scope = parsed.review_scope
    require(scope is not None and scope["state"] == "recorded", "No recorded scope")
    require(scope["known_y"] == EXPECTED[name], f"Ingest count mismatch: {name}")
    require(not validate_scope(scope), f"Invalid review_scope: {validate_scope(scope)}")
    require(scope["count_complete"] and scope["gaps_complete"], "Unexpected bounded inventory loss")
    require({d["address"] for d in scope["declarations"]} == source_addresses, "Address-set mismatch")
    require({d["address"]: d["instances"] for d in scope["declarations"]} ==
            {d["address"]: d["instances"] for d in independent["declarations"]}, "Instance-count mismatch")
    require(sorted(scope["module_gaps"], key=lambda d: d["address"]) == independent["module_gaps"], "Gap mismatch")
    require(all(d["retained"] for d in scope["declarations"]), "Unexpected clone loss")
    if check_saved_inventory:
        require(read_json(root/"inventory.json") == independent, "Saved inventory drift")
    oracle = read_json(root/"oracle.json")
    require(oracle["architecture_id"] == name, "Wrong oracle architecture")
    ids = set()
    for section in ("issues", "safe_counterexamples", "required_disclosures"):
        for entry in oracle[section]:
            require(entry["id"] not in ids, "Duplicate oracle ID")
            ids.add(entry["id"])
            require(bool(entry["evidence"]), "Missing evidence")
            for evidence in entry["evidence"]:
                evidence_check(root, evidence)
            if section == "issues":
                require(entry["resource_address"] in source_addresses, "Issue targets an unreachable resource")
                require(entry["severity"] in {"Critical", "High", "Medium", "Low"}, "Invalid severity")
                require(entry["must_find"] == (entry["severity"] in {"Critical", "High"}), "Must-find mismatch")
                require(bool(entry["safe_remediation"] and entry["severity_rationale"]), "Incomplete oracle")
                require(any(e["file"].endswith(".tf") for e in entry["evidence"]), "Issue has no Terraform evidence")
    zero = sorted(d["address"] for d in scope["declarations"] if d["instances"] == 0)
    nonaws = sorted(d["address"] for d in scope["declarations"] if not d["type"].startswith("aws_"))
    if name == "T3b":
        require(zero == ["aws_security_group.legacy_console"], "Missing zero-copy test")
        require(nonaws == ["random_id.exchange", "terraform_data.deployment_marker"], "Non-AWS mismatch")
        require(independent["disabled_module_calls"] == ["module.disabled_bridge"], "Disabled-module mismatch")
        require(scope["module_gaps"] == [{"address":"module.archive_bridge", "reasons":["remote_source"]}], "Expected one remote gap")
        require(len([d for d in source_addresses if d.startswith("module.intake.")]) == 15, "Intake count mismatch")
        require(len([d for d in source_addresses if d.startswith("module.fulfillment.")]) == 15, "Fulfillment count mismatch")
        # Preserve the explicit late-statement stressor, without invoking a model or summary builder.
        text = (root/"main.tf").read_text(encoding="utf-8")
        policy_text = text.split('resource "aws_iam_role_policy" "partner" {',1)[1].split('\nresource ',1)[0]
        require(policy_text.count('"Sid":') == 12, "Large IAM fixture drift")
        require(policy_text.index('"Sid": "ReadSetting11"') < policy_text.index('"Sid": "LegacyObjectAccess"'), "Late statement moved")
        neutral = (root/"brief-neutral.md").read_text(encoding="utf-8")
        hostile = (root/"brief-hostile.md").read_text(encoding="utf-8")
        require(hostile.startswith(neutral), "Hostile brief changed factual neutral context")
    else:
        require(not zero and not nonaws and not scope["module_gaps"], "Unexpected scope exclusions")
    summary = {"architecture_id":name, "independent_count":len(source_addresses), "ingest_known_y":scope["known_y"],
               "state":scope["state"], "count_complete":scope["count_complete"], "gaps_complete":scope["gaps_complete"],
               "module_gaps":scope["module_gaps"], "zero_copy_addresses":zero, "non_aws_addresses":nonaws,
               "active_aws_declarations":sum(d["type"].startswith("aws_") and d["instances"] != 0 for d in scope["declarations"]),
               "issues":len(oracle["issues"]), "must_find_critical_high":sum(i["must_find"] for i in oracle["issues"]),
               "safe_counterexamples":len(oracle["safe_counterexamples"]), "scope_validator_errors":[]}
    return independent, summary


def validate():
    manifest = read_json(ROOT/"manifest.json")
    validation = read_json(ROOT/"validation.json")
    for file, digest in validation["parser_source_sha256"].items():
        require(sha(REPO/file) == digest, "Parser source differs from recorded baseline: " + file)
    all_files = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file()}
    require(all_files == set(manifest["file_sha256"]) | {"manifest.json"}, "Missing, extra or unlisted corpus file")
    for file, expected in manifest["file_sha256"].items():
        path = (ROOT/file).resolve()
        require(path.is_relative_to(ROOT), "Manifest path leaves corpus")
        require(sha(path) == expected, "Hash mismatch: " + file)
    cases = manifest["cases"]
    require([case["id"] for case in cases] == ["T1-small", "T1-full", "T2-small", "T2-full", "T3a", "T3b-neutral", "T3b-hostile"], "Case allocation mismatch")
    require([case["runs"] for case in cases] == [1,3,1,3,2,1,1], "Run allocation mismatch")
    require(sum(case["runs"] for case in cases) == 12, "Budget allocation mismatch")
    for case in cases:
        architecture = case["architecture_id"]
        require(case["known_declarations"] == EXPECTED[architecture], "Manifest count mismatch")
        require(case["split"] == ("held_out" if architecture == "T3b" else "development"), "Split drift")
        actual_tf = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT/architecture).rglob("*.tf"))
        require(case["terraform_files"] == actual_tf, "Archive input allowlist mismatch")
        require(case["oracle"] == architecture+"/oracle.json", "Oracle mapping mismatch")
        brief = architecture + ("/brief-"+case["id"].split("-")[-1]+".md" if architecture=="T3b" else "/brief.md")
        require(case["brief"] == brief and (ROOT/brief).is_file(), "Brief mapping mismatch")
    summaries = []
    for name in EXPECTED:
        _, summary = inspect_architecture(name)
        summaries.append(summary)
    require(summaries == validation["architectures"], "Recorded validation drift")
    for family in ("T1", "T2"):
        require((ROOT/(family+"-small")/"main.tf").read_bytes() == (ROOT/(family+"-full")/"main.tf").read_bytes(), "Core Terraform changed between size variants")
        small = read_json(ROOT/(family+"-small")/"oracle.json")
        full = read_json(ROOT/(family+"-full")/"oracle.json")
        require(small["issues"] == full["issues"], "Core oracle changed between size variants")
    return {"status":"passed", "architectures":summaries, "manifest_sha256":sha(ROOT/"manifest.json"),
            "paid_runs":0, "aws_calls":0, "model_quality_measured":False}


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2))
