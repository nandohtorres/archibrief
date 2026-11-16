"""Recover P1 request sizes; optionally validate with unbilled CountTokens.

Default is entirely local. --count-tokens makes only AWS CountTokens requests,
never embeddings, Guardrails or generation. Output is measurements, not content.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.agent.request_budget import generation_request, prepare_envelope
from backend.shared.model_request_budget import (
    MAX_EVIDENCE_BYTES,
    MAX_REQUEST_BYTES,
    POLICY_VERSION,
    count_input_tokens,
    evidence_bytes,
    generation_cost_micro_usd,
    request_utf8_bytes,
)


def recovered_requests(root: Path = ROOT) -> list[tuple[int, dict, dict, dict]]:
    folder = root / "backend/build/evaluations/p1"
    runs = json.loads((folder / "runs.json").read_text())
    chunks = {}
    for file in (root / "backend/corpus/data/chunks").glob("*.json"):
        for chunk in json.loads(file.read_text(encoding="utf-8")):
            heading = chunk["heading_path"]
            chunks[chunk["chunk_id"]] = {
                **chunk,
                "heading_path": " > ".join(heading)
                if isinstance(heading, list)
                else heading,
            }
    results = []
    for slot in (6, 8, 9, 10, 11, 12):
        ledger = json.loads((folder / "ledgers" / f"{slot}.json").read_text())
        model = [f for f in ledger["findings"] if f.get("model_id")]
        ids = model[0]["retrieved_chunk_ids"]
        if any(f["retrieved_chunk_ids"] != ids for f in model):
            raise ValueError("inconsistent retained retrieval lists")
        for finding in model:
            citation = finding.get("citation")
            if (
                citation
                and citation["content_hash"]
                != chunks[citation["chunk_id"]]["content_hash"]
            ):
                raise ValueError("local corpus differs from recorded citation hash")
        payload = {
            "review_id": ledger["review_id"],
            "workload_brief": ledger["workload_brief"],
            "retrieval_query": ledger["workload_brief"],
            "baseline_answers": {
                a["field"]: a["value"]
                for a in ledger["baseline_answers"]
                if a.get("outcome") == "answered"
            },
            "rule_findings": [f for f in ledger["findings"] if not f.get("model_id")],
            "terraform_resources": ledger["terraform_resources"],
        }
        evidence = [chunks[cid] for cid in ids]
        full = generation_request(payload, evidence)
        actual_chars = len(full["messages"][0]["content"][0]["text"])
        expected_chars = runs[ledger["review_id"]]["input_chars"]
        if actual_chars != expected_chars:
            raise ValueError(
                f"slot {slot}: reconstructed input length differs from recorded input"
            )
        metadata = {
            "slot": slot,
            "user_chars_match": True,
            "request_bytes": request_utf8_bytes(full),
            "evidence_bytes": evidence_bytes(evidence),
            "size_admitted": request_utf8_bytes(full) <= MAX_REQUEST_BYTES
            and evidence_bytes(evidence) <= MAX_EVIDENCE_BYTES,
        }
        results.append((slot, payload, full, metadata))
        metadata["pre_retrieval_bound_bytes"] = (
            request_utf8_bytes(generation_request(payload, [])) + MAX_EVIDENCE_BYTES
        )
        metadata["byte_envelope_admitted"] = (
            metadata["pre_retrieval_bound_bytes"] <= MAX_REQUEST_BYTES
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count-tokens", action="store_true")
    parser.add_argument("--profile", default="archibrief-deploy")
    args = parser.parse_args()
    counter = None
    if args.count_tokens:
        import boto3
        from botocore.config import Config

        counter = boto3.Session(
            profile_name=args.profile, region_name="us-east-1"
        ).client(
            "bedrock-runtime",
            config=Config(
                connect_timeout=2, read_timeout=15, retries={"total_max_attempts": 1}
            ),
        )
    rows = []
    cache = {}
    attempts = []

    class Counter:
        def count_tokens(self, **kwargs):
            key = hashlib.sha256(
                json.dumps(kwargs, sort_keys=True).encode()
            ).hexdigest()
            if key not in cache:
                attempts.append(key)
                cache[key] = counter.count_tokens(**kwargs)
            return cache[key]

    for _slot, payload, full, metadata in recovered_requests():
        row = dict(metadata)
        if counter is not None:
            try:
                row["full_input_tokens"] = count_input_tokens(Counter(), full)
                row["generation_worst_case_micro_usd"] = (
                    generation_cost_micro_usd(
                        row["full_input_tokens"], full["inferenceConfig"]["maxTokens"]
                    )
                    + 20000
                )
                row["pre_retrieval"] = prepare_envelope(payload, Counter(), 400000)
                row["cost_admitted"] = row["generation_worst_case_micro_usd"] <= 400000
            except Exception as exc:  # noqa: BLE001 - disclose failure without request content
                row["count_error"] = type(exc).__name__
                row["code"] = getattr(exc, "code", "unavailable")
                row["aws_error_code"] = (
                    getattr(exc.__cause__, "response", {}).get("Error", {}).get("Code")
                )
                row["cost_admitted"] = False
        rows.append(row)
        if row.get("cost_admitted") is False:
            break
    print(
        json.dumps(
            {
                "policy": POLICY_VERSION,
                "requests": rows,
                "count_tokens_calls": len(attempts),
                "paid_calls": 0,
                "original_full_request_hash_available": False,
            },
            indent=2,
        )
    )
    return int(
        any(
            not r["size_admitted"]
            or not r["byte_envelope_admitted"]
            or r.get("cost_admitted") is False
            for r in rows
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
