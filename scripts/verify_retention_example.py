"""Verify the owned before/after example with actual static rules; no AWS calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.lambdas.ingest.handler import parse_terraform_files
from backend.lambdas.rule_engine.handler import RULE_VERSION, run_rules


def findings(path):
    parsed = asdict(parse_terraform_files([str(path)]))
    return [
        {
            key: finding.model_dump(mode="json")[key]
            for key in (
                "concern",
                "category",
                "type",
                "finding",
                "evidence",
                "risk_impact",
                "recommendation",
            )
        }
        for finding in run_rules(parsed, "retention-example")
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    directory = ROOT / "docs/examples/retention-remediation"
    before, after = findings(directory / "before.tf"), findings(directory / "after.tf")
    key = lambda finding: json.dumps(finding, sort_keys=True)
    previous, current = Counter(map(key, before)), Counter(map(key, after))
    removed = [json.loads(item) for item in (previous - current).elements()]
    added = [json.loads(item) for item in (current - previous).elements()]
    passed = (
        len(removed) == 1
        and removed[0]["concern"] == "versioned_retention_gap"
        and not added
    )
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "deterministic-static-example",
        "rule_version": RULE_VERSION,
        "passed": passed,
        "paid_calls": 0,
        "terraform_executed": False,
        "model_quality_measured": False,
        "source_sha256": {
            name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in ("before.tf", "after.tf")
        },
        "removed": removed,
        "added": added,
        "unchanged_count": sum((previous & current).values()),
        "before": before,
        "after": after,
    }
    if args.out:
        with args.out.open("x", encoding="utf-8") as output:
            json.dump(result, output, indent=2)
            output.write("\n")
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "passed",
                    "paid_calls",
                    "model_quality_measured",
                    "unchanged_count",
                )
            }
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
