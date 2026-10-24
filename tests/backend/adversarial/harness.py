"""Runs an adversarial fixture through ArchiBrief's real deterministic path
and judges it against the frozen answer key.

The path is the deployed one, minus AWS: the fixture directory is packed
into a tar, unpacked by extract_archive (the same bounds and suffix
allowlist Ingest and Scan use), parsed by parse_terraform_files, optionally
scanned by an offline Trivy with the scanner's own isolation, then passed to
run_rules, build_resource_summary, build_architecture and
build_review_report. Nothing here calls AWS, a model, or terraform.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tarfile
from dataclasses import asdict, dataclass
from pathlib import Path

from backend.lambdas.ingest.handler import extract_archive, parse_terraform_files
from backend.lambdas.rule_engine.architecture import build_architecture
from backend.lambdas.rule_engine.handler import run_rules
from backend.lambdas.rule_engine.resource_summary import build_resource_summary
from backend.lambdas.scan.handler import neutralize_remote_sources, scan_files
from backend.shared.report import build_review_report
from backend.shared.terraform_scope import display_name

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures"
ANSWER_KEY = HERE / "answer_key.json"
FROZEN = HERE / "FROZEN.sha256"
TERRAFORM_SUFFIXES = (".tf", ".tfvars", ".hcl")


def trivy_path() -> str | None:
    configured = os.environ.get("TRIVY_PATH")
    if configured and Path(configured).exists():
        return configured
    return shutil.which("trivy")


def load_answer_key() -> dict:
    """The answer key, refusing to load if it changed after it was frozen."""
    digest = hashlib.sha256(ANSWER_KEY.read_bytes()).hexdigest()
    frozen = FROZEN.read_text(encoding="utf-8").strip()
    if digest != frozen:
        raise RuntimeError(
            f"answer_key.json changed after it was frozen ({digest} != {frozen}). "
            "Record the reason in README.md and refreeze deliberately."
        )
    return json.loads(ANSWER_KEY.read_text(encoding="utf-8"))


def pack(fixture: Path, archive: Path) -> None:
    """A tar of the fixture's Terraform files, paths relative to its root."""
    with tarfile.open(archive, "w") as tar:
        for path in sorted(fixture.rglob("*")):
            if path.is_file() and path.suffix in TERRAFORM_SUFFIXES:
                tar.add(path, arcname=path.relative_to(fixture).as_posix())


@dataclass
class Run:
    mode: str
    parsed: dict
    findings: list[dict]
    summary: dict
    graph: dict
    report: dict
    scanner: dict | None


def run_fixture(
    fixture: str,
    mode: str,
    work: Path,
    brief: str = "",
    *,
    review_id: str = "adversarial",
) -> Run:
    source = FIXTURES / fixture
    work.mkdir(parents=True, exist_ok=True)
    archive = work / "submission.tar"
    pack(source, archive)
    extracted_dir = work / "extracted"
    files = extract_archive(str(archive), str(extracted_dir))
    parsed = asdict(parse_terraform_files(sorted(files)))

    scanner = None
    if mode == "trivy":
        binary = trivy_path()
        if binary is None:
            raise RuntimeError("Trivy not installed (set TRIVY_PATH)")
        # The scanner works on its own extraction, as the Scan Lambda does.
        scan_dir = work / "scan"
        scan_files_list = extract_archive(str(archive), str(scan_dir))
        scanner = scan_files(str(scan_dir), sorted(scan_files_list), binary)

    findings = [
        f.model_dump(mode="json") for f in run_rules(parsed, review_id, scanner=scanner)
    ]
    summary = build_resource_summary(parsed)
    graph = build_architecture(parsed, findings)
    report = build_review_report(
        {"reviewId": review_id, "terraformRepoRef": fixture},
        {
            "findings": findings,
            "terraform_resources": summary,
            "baseline_answers": [],
            "architecture": graph,
        },
    )
    return Run(mode, parsed, findings, summary, graph, report, scanner)


# --- Probes ----------------------------------------------------------------


def _finding_text(finding: dict) -> str:
    return " ".join(
        str(finding.get(k) or "")
        for k in ("finding", "evidence", "risk_impact", "recommendation")
    )


def _entries(run: Run, resource_type: str, name: str) -> list[dict]:
    return [
        e
        for e in run.summary.get("resources", [])
        if e.get("type") == resource_type and e.get("name") == name
    ]


def probe(spec: dict, run: Run, context: dict) -> tuple[bool, str]:
    """(matched, what was observed) for one probe of the answer key."""
    if "any_of" in spec:
        observed = []
        for sub in spec["any_of"]:
            matched, detail = probe(sub, run, context)
            observed.append(detail)
            if matched:
                return True, detail
        return False, " | ".join(observed)

    if "finding" in spec:
        needles = [n.lower() for n in spec["finding"]]
        hedges = [h.lower() for h in spec.get("unless_any", [])]
        hits = []
        for f in run.findings:
            text = _finding_text(f).lower()
            if all(n in text for n in needles) and not any(h in text for h in hedges):
                hits.append(f["finding"])
        if hits:
            return True, f"finding: {hits[0][:160]}"
        return False, f"no finding with {spec['finding']}"

    if "summary_setting" in spec:
        s = spec["summary_setting"]
        entries = _entries(run, s["type"], s["name"])
        if not entries:
            return False, f"no summary entry {s['type']}.{s['name']}"
        value = entries[0]["settings"].get(s["setting"], "<absent>")
        expected = s["equals"]
        matched = value == expected and type(value) is type(expected)
        return matched, f"summary {s['name']}.{s['setting']} = {value!r}"

    if "summary_entry" in spec:
        s = spec["summary_entry"]
        entries = _entries(run, s["type"], s["name"])
        if not entries:
            return False, f"no summary entry {s['type']}.{s['name']}"
        if "copies" in s:
            copies = entries[0].get("copies")
            return copies == s["copies"], f"summary {s['name']} copies = {copies!r}"
        return True, f"summary entry {s['type']}.{s['name']} present"

    if "summary_entry_text" in spec:
        s = spec["summary_entry_text"]
        entries = _entries(run, s["type"], s["name"])
        if not entries:
            return False, f"no summary entry {s['type']}.{s['name']}"
        text = json.dumps(entries[0]).lower()
        hits = [n for n in s["contains_any"] if n.lower() in text]
        return bool(hits), f"summary {s['name']}: {json.dumps(entries[0])[:200]}"

    if "backup_rules_complete" in spec:
        s = spec["backup_rules_complete"]
        entries = _entries(run, "aws_backup_plan", s["name"])
        if not entries:
            return False, f"no summary entry aws_backup_plan.{s['name']}"
        rules = entries[0].get("rules", [])
        flagged = any("truncat" in k.lower() for k in entries[0])
        complete = len(rules) == s["expected_rules"] or flagged
        return (
            complete,
            f"summary shows {len(rules)} of {s['expected_rules']} rules, truncation flag: {flagged}",
        )

    if "not_observable" in spec:
        gaps = [str(g).lower() for g in run.parsed.get("not_observable", [])]
        missing = [
            n for n in spec["not_observable"] if not any(n.lower() in g for g in gaps)
        ]
        return not missing, f"not_observable = {run.parsed.get('not_observable', [])}"

    if "graph_edge" in spec:
        edge = {"from": spec["graph_edge"]["from"], "to": spec["graph_edge"]["to"]}
        edges = run.graph.get("edges", [])
        return edge in edges, f"{len(edges)} edges; internet edges: " + ", ".join(
            e["to"] for e in edges if e["from"] == "internet"
        )

    if "text_present" in spec:
        s = spec["text_present"]
        artifacts = {
            "summary": run.summary,
            "findings": run.findings,
            "graph": run.graph,
            "report": run.report,
            "parsed": run.parsed,
        }
        hits = []
        for where in s["where"]:
            blob = json.dumps(artifacts[where], ensure_ascii=False).lower()
            hits += [f"{n!r} in {where}" for n in s["needles"] if n.lower() in blob]
        return bool(hits), ("; ".join(hits) if hits else "none of the needles present")

    if "names_distinct" in spec:
        a, b = (display_name(k) for k in spec["names_distinct"])
        return a != b, f"display names: {a!r} vs {b!r}"

    if "neutralized" in spec:
        copy = context["work"] / "neutralize"
        shutil.copytree(FIXTURES / context["fixture"], copy, dirs_exist_ok=True)
        files = [str(p) for p in copy.rglob("*.tf")]
        neutralize_remote_sources(files, str(copy))
        leftover = []
        for path in files:
            for line in Path(path).read_text(encoding="utf-8").splitlines():
                if re.search(r"\bsource\s*=", line) and any(
                    n in line for n in spec["neutralized"]
                ):
                    leftover.append(line.strip())
        return not leftover, (
            "left in place: " + " | ".join(leftover)
        ) if leftover else "all rewritten"

    if "stable_against" in spec:
        other = context["run_other"](spec["stable_against"], run.mode)
        mine = sorted(f["finding"] for f in run.findings)
        theirs = sorted(f["finding"] for f in other.findings)
        only_mine = sorted(set(mine) - set(theirs))
        only_theirs = sorted(set(theirs) - set(mine))
        same = mine == theirs
        return same, (
            "identical finding set"
            if same
            else f"only here: {only_mine[:3]}; only in control: {only_theirs[:3]}"
        )

    raise ValueError(f"unknown probe {spec}")


def judge(kind: str, matched: bool) -> str:
    if kind == "acceptable_uncertainty":
        return "pass (acceptable either way)"
    if kind in ("must_detect", "must_disclose"):
        return "pass" if matched else "fail"
    if kind == "must_not_claim":
        return "fail" if matched else "pass"
    raise ValueError(kind)
