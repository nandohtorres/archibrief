"""Rebuild frozen sample uploads and report offline rule/fact expectations.

No AWS clients, generation, embeddings or Terraform execution. Existing oracles
remain unchanged. This is a development regression check, not fresh evaluation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.lambdas.rule_engine.handler import RULE_VERSION
from backend.shared.review_limits import scope_rejection_code
from scripts.small_workload_eval import CORPUS, build_archive, load_manifest
from tests.backend.adversarial.harness import trivy_path
from tests.backend.p1_guards import CASE_ISSUES, replay_case


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scanner", default=trivy_path())
    args = parser.parse_args()
    if not args.scanner:
        parser.error(
            "An installed Trivy executable is required for complete rule checks"
        )
    manifest = load_manifest()
    args.output.mkdir(parents=True, exist_ok=True)
    cases = []
    failures = []
    for case in manifest["cases"]:
        case_id = case["id"]
        replay = replay_case(case, CORPUS, args.scanner)
        if not replay.scanner or replay.scanner.get("status") != "ok":
            failures.append(f"{case_id}: scanner unavailable; rule checks incomplete")
        scope = replay.parsed["review_scope"]
        eligibility = scope_rejection_code(scope)
        if scope["known_y"] != case["known_declarations"] or eligibility:
            failures.append(f"{case_id}: declaration count or scope admission drift")
        checks = []
        expectations = CASE_ISSUES.get(case_id, {})
        oracle = json.loads((CORPUS / case["oracle"]).read_text(encoding="utf-8"))
        for issue in oracle["issues"]:
            known = expectations.get(issue["id"])
            rule_match = (
                replay.rule_catches(*known.rule) if known and known.rule else None
            )
            facts = [
                {
                    **asdict(fact),
                    "observed": replay.fact(fact.type, fact.name, fact.setting),
                    "matches": replay.fact(fact.type, fact.name, fact.setting)
                    == fact.value,
                }
                for fact in (known.facts if known else ())
            ]
            if rule_match is False or any(not fact["matches"] for fact in facts):
                failures.append(f"{case_id}: {issue['id']} rule/fact regression")
            checks.append(
                {
                    "id": issue["id"],
                    "severity": issue["severity"],
                    "resource": issue["resource_address"],
                    "expected_finding": issue["expected_finding"],
                    "safe_remediation": issue.get("safe_remediation"),
                    "expected_rule": list(known.rule) if known and known.rule else None,
                    "rule_matches": rule_match,
                    "required_facts": facts,
                    "semantic_model_judgment": "not_run",
                }
            )
        archive = build_archive(CORPUS, case, args.output / f"{case_id}.tar.gz")
        cases.append(
            {
                "case": case_id,
                "split": "development_exposed",  # T3b has already been reviewed in detail.
                "scope": scope,
                "scope_rejection_code": eligibility,
                "scanner_status": (replay.scanner or {}).get("status"),
                "archive": archive.name,
                "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                "brief": case["brief"],
                "issues": checks,
                "counterexamples_for_manual_review": oracle.get(
                    "safe_counterexamples", []
                ),
                "current_rules": replay.rules,
            }
        )
    result = {
        "rule_version": RULE_VERSION,
        "fixture_manifest_sha256": manifest["_sha256"],
        "method": "Frozen sample replay: deterministic rule/fact and scope checks only",
        "fresh_holdout": False,
        "model_quality_measured": False,
        "aws_calls": 0,
        "paid_calls": 0,
        "candidate_source_sha256": {
            relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            for relative in (
                "backend/lambdas/ingest/handler.py",
                "backend/lambdas/rule_engine/handler.py",
                "backend/lambdas/rule_engine/resource_summary.py",
                "backend/shared/recommendation_checks.py",
            )
        },
        "failures": failures,
        "cases": cases,
    }
    (args.output / "report.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Sample architecture regression checks",
        "",
        "Frozen inputs and expectations; no live AI or semantic accuracy score.",
        "T3b is exposed development data and is no longer a fresh holdout.",
        "",
    ]
    for case in cases:
        lines += [
            f"## {case['case']}",
            "",
            f"Upload: `{case['archive']}` (Terraform only); brief: `{case['brief']}`.",
            f"Known declarations: {case['scope']['known_y']}; scope admission: {case['scope_rejection_code'] or 'eligible (not authorization)'}.",
            "",
        ]
        for issue in case["issues"]:
            check = "matched" if issue["rule_matches"] else "not automatically scored"
            lines += [
                f"- **{issue['id']} ({issue['severity']})**: {issue['expected_finding']}",
                f"  Deterministic expectation: {check}. Model judgment: not run.",
            ]
        lines += [""]
    lines += [
        "## Failures",
        "",
        *(failures or ["None in the checked rule/fact/scope expectations."]),
    ]
    (args.output / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "cases": len(cases),
                "failures": failures,
                "paid_calls": 0,
                "report": str(args.output / "report.json"),
            },
            indent=2,
        )
    )
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
