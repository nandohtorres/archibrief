"""Offline replay of published P1 findings against the local repaired candidate.

No model/embedding/Guardrails/CountTokens calls. This is a regression diagnostic,
not a live accuracy evaluation or a claim about unseen model output.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.agent.nodes.reason import PROMPT_VERSION, verify_model_findings
from backend.agent.request_budget import generation_request
from backend.lambdas.rule_engine.handler import RULE_VERSION
from backend.shared.model_request_budget import (
    MAX_EVIDENCE_BYTES,
    MAX_REQUEST_BYTES,
    request_utf8_bytes,
)
from backend.shared.recommendation_checks import REMEDIATION_POLICY_VERSION
from scripts.check_p2_request_budget import recovered_requests
from scripts.small_workload_eval import CORPUS, case_by_id, load_manifest
from tests.backend.p1_guards import CASE_ISSUES, covered_issues, replay_case

SLOTS = {
    6: "T3b-neutral",
    8: "T3a",
    9: "T1-full",
    10: "T2-full",
    11: "T1-full",
    12: "T2-full",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scanner", default=shutil.which("trivy"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases = case_by_id(load_manifest())
    cache = {}
    rows = []
    for slot, old_payload, full, _measurement in recovered_requests():
        case_id = SLOTS[slot]
        if case_id not in cache:
            cache[case_id] = replay_case(cases[case_id], CORPUS, args.scanner)
        replay = cache[case_id]
        ledger = json.loads(
            (ROOT / f"backend/build/evaluations/p1/ledgers/{slot}.json").read_text()
        )
        evidence = json.loads(full["messages"][0]["content"][0]["text"])[
            "retrieved_evidence"
        ]
        # Resolve original complete chunk metadata; no new retrieval or changed text.
        chunks = {}
        for path in (ROOT / "backend/corpus/data/chunks").glob("*.json"):
            for chunk in json.loads(path.read_text(encoding="utf-8")):
                heading = chunk.get("heading_path", [])
                chunk["heading_path"] = (
                    " > ".join(heading) if isinstance(heading, list) else heading
                )
                chunks[chunk["chunk_id"]] = chunk
        retained = []
        dropped = []
        corrected = []
        retrieved = [chunks[c["chunk_id"]] for c in evidence]
        for finding in ledger["findings"]:
            if not finding.get("model_id"):
                continue
            citation = finding.get("citation") or {}
            raw = {
                **finding,
                "chunk_id": citation.get("chunk_id"),
                "exact_quote": citation.get("exact_text_span"),
            }
            accepted, errors = verify_model_findings(
                [raw],
                ledger["review_id"],
                finding["model_id"],
                finding["corpus_version"],
                retrieved,
                RULE_VERSION,
                terraform_resources=replay.summary,
                authoritative_rule_findings=replay.rules,
            )
            if accepted:
                verified = accepted[0].model_dump(mode="json")
                retained.append({**verified, "finding_id": finding["finding_id"]})
                if verified["recommendation"] != finding["recommendation"]:
                    corrected.append(
                        {
                            "finding_id": finding["finding_id"],
                            "kind": "explicit_ebs_safety_correction",
                        }
                    )
            else:
                dropped.append({"finding_id": finding["finding_id"], "reasons": errors})
        payload = {
            **old_payload,
            "rule_findings": replay.rules,
            "terraform_resources": replay.summary,
        }
        # Reuse exactly the historical supplied passages for byte diagnostics.
        for chunk in retrieved:
            heading = chunk.get("heading_path", [])
            chunk["heading_path"] = (
                " > ".join(heading) if isinstance(heading, list) else heading
            )
        actual = request_utf8_bytes(generation_request(payload, retrieved))
        bound = request_utf8_bytes(generation_request(payload, [])) + MAX_EVIDENCE_BYTES
        issues = CASE_ISSUES.get(case_id)
        lost = None
        lost_severe = None
        if issues:
            before = covered_issues(ledger["findings"], issues)
            after = covered_issues([*replay.rules, *retained], issues)
            lost = sorted(before - after)
            lost_severe = [
                key
                for key in lost
                if issues[key].severity.lower() in {"critical", "high"}
            ]
        rows.append(
            {
                "slot": slot,
                "case": case_id,
                "retained_published_model_findings": len(retained),
                "dropped_published_model_findings": dropped,
                "corrected_published_model_findings": corrected,
                "current_rule_count": len(replay.rules),
                "request_bytes_with_historical_passages": actual,
                "pre_retrieval_bound_bytes": bound,
                "byte_admitted": actual <= MAX_REQUEST_BYTES
                and bound <= MAX_REQUEST_BYTES,
                "keyword_coverage_regressions": lost,
                "keyword_critical_high_regressions": lost_severe,
            }
        )
    result = {
        "rule_version": RULE_VERSION,
        "model_input_version": PROMPT_VERSION,
        "remediation_policy_version": REMEDIATION_POLICY_VERSION,
        "scanner_used": bool(args.scanner),
        "paid_calls": 0,
        "method": "Published-output replay and keyword diagnostics only; no live generation, semantic regrade or cost validation.",
        "rows": rows,
    }
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return int(
        any(
            not row["byte_admitted"] or row["keyword_critical_high_regressions"]
            for row in rows
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
