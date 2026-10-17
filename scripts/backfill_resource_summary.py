"""Add the resource summary to reviews stored before Finalize kept it.

Finalize writes RuleEngine's resource summary (ADR-0049)
into each review's evidence ledger, so the report chat answers from the
same facts the review saw (ADR-0050). Reviews stored before that, the
demos among them, have none, and the chat says settings aren't
determinable. This rebuilds the summary from the review's own parsed
Terraform (`parsed/<review_id>.json`, written by Ingest) with the same
code RuleEngine runs, and adds it to the ledger. Nothing else in the
ledger changes.

    python scripts/backfill_resource_summary.py <review_id> ...          # dry run
    python scripts/backfill_resource_summary.py --apply <review_id> ...  # writes S3

Dry run by default: it prints what it would add. --apply overwrites the
ledger object in the reports bucket and requires explicit approval. Only
S3 reads and writes are made; no model is called.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.lambdas.rule_engine.resource_summary import (
    build_resource_summary,
)

BUCKET = "archibrief-dev-source-of-truth"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("review_ids", nargs="+")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--bucket", default=BUCKET)
    args = parser.parse_args()
    s3 = boto3.client("s3")
    for review_id in args.review_ids:
        ledger_key = f"reports/{review_id}/evidence-ledger.json"
        ledger = json.loads(
            s3.get_object(Bucket=args.bucket, Key=ledger_key)["Body"].read()
        )
        if ledger.get("terraform_resources"):
            print(f"{review_id}: already has a resource summary")
            continue
        parsed = json.loads(
            s3.get_object(Bucket=args.bucket, Key=f"parsed/{review_id}.json")[
                "Body"
            ].read()
        )
        summary = build_resource_summary(parsed)
        print(
            f"{review_id}: {len(summary['resources'])} resources"
            f"{' (truncated)' if summary['truncated'] else ''}"
        )
        if args.apply:
            ledger["terraform_resources"] = summary
            s3.put_object(
                Bucket=args.bucket,
                Key=ledger_key,
                Body=json.dumps(ledger).encode("utf-8"),
                ContentType="application/json",
            )
            print(f"{review_id}: ledger updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
