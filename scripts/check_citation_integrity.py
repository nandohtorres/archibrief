"""Audit saved P1 citations locally and produce an ungraded entailment worksheet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.shared.citation_integrity import citation_errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    chunks = {}
    for path in sorted((ROOT / "backend/corpus/data/chunks").glob("*.json")):
        for chunk in json.loads(path.read_text(encoding="utf-8")):
            key = chunk["chunk_id"]
            if key in chunks and chunks[key] != chunk:
                raise ValueError("conflicting local chunk ID")
            chunks[key] = chunk
    if not chunks:
        raise ValueError("local corpus chunks required")
    rows = []
    for slot in (6, 8, 9, 10, 11, 12):
        path = ROOT / f"backend/build/evaluations/p1/ledgers/{slot}.json"
        ledger = json.loads(path.read_text(encoding="utf-8"))
        for finding in ledger["findings"]:
            if not finding.get("model_id"):
                continue
            citation = finding.get("citation") or {}
            rows.append(
                {
                    "slot": slot,
                    "finding_id": finding["finding_id"],
                    "finding": finding["finding"],
                    "risk_impact": finding["risk_impact"],
                    "recommendation": finding["recommendation"],
                    "evidence": finding["evidence"],
                    "citation": citation,
                    "source_passage": chunks.get(citation.get("chunk_id"), {}).get(
                        "text"
                    ),
                    "integrity_errors": citation_errors(finding, chunks),
                    "semantic_entailment": "unreviewed",
                    "remediation_applicability": "unreviewed",
                }
            )
    result = {
        "method": "Local quote/hash/metadata checks only; no entailment score",
        "model_calls": 0,
        "paid_calls": 0,
        "rows": rows,
        "checked": len(rows),
        "integrity_failures": sum(bool(r["integrity_errors"]) for r in rows),
        "semantic_reviews_completed": 0,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "citation-integrity.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Citation semantic review worksheet",
        "",
        "Check each full claim and proposed action against configuration AND the quoted source.",
        "Exact quote/hash matches do not prove relevance or applicability. All rows remain ungraded.",
        "",
    ]
    for row in rows:
        lines += [
            f"## Slot {row['slot']}: {row['finding_id']}",
            "",
            f"Finding: {row['finding']}",
            f"Evidence: {row['evidence']}",
            f"Risk: {row['risk_impact']}",
            f"Proposed action: {row['recommendation']}",
            "",
            f"Source: {row['citation'].get('source_url')}",
            f"Quoted: {row['citation'].get('exact_text_span')}",
            "",
            f"Full supplied passage: {row['source_passage']}",
            "",
            "Judgment: UNREVIEWED. Does the source support this claim and fix for this configuration?",
            "",
        ]
    (args.output / "citation-entailment-worksheet.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))
    return int(result["integrity_failures"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
