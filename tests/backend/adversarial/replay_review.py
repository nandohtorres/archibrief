"""Free local contract replay through production functions and the real graph.

Usage: python -m tests.backend.adversarial.replay_review --case F07-dangerous
       --transcript private-recorded-responses.json --out private-fresh-result.json

Only SDK responses are replayed. Nothing constructs an AWS client, calls a
model, runs Terraform, writes a remote ledger or proves semantic correctness.
Output contains raw responses: keep it private and inspect before sharing.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from copy import deepcopy
from pathlib import Path

from backend.agent.graph import compiled_graph
from backend.lambdas.finalize.handler import (
    assemble_baseline_answers,
    assemble_evidence_ledger,
    place_findings,
)
from backend.lambdas.validate.handler import validate_findings
from backend.shared.analysis_quality import build_analysis_quality
from backend.shared.report import build_review_report
from tests.backend.adversarial.harness import load_answer_key, run_fixture
from tests.backend.adversarial.semantic_oracle import (
    load_semantic_oracle,
    semantic_review,
)


class RecordedServices:
    """SDK-shaped recorded responses; no SDK client or network fallback."""

    model_id = "offline-recorded-response"

    def __init__(self, transcript: dict):
        self.transcript = transcript
        self.calls: list[str] = []
        self.screened_input: str | None = None
        self.model_input: dict | None = None
        self.model_response = None

    def _call(self, name):
        self.calls.append(name)
        if self.transcript.get("fail_at") == name:
            raise RuntimeError("recorded service failure")

    def embed(self, text):
        self._call("embedding")
        return [0.0]

    def query_vectors(self, **kwargs):
        self._call("vectors")
        return deepcopy(self.transcript["vector_matches"])

    def check(self, text, **kwargs):
        self._call("guardrail")
        self.screened_input = text
        allowed = self.transcript["guardrail_allowed"]
        if type(allowed) is not bool:
            raise ValueError("recorded guardrail outcome must be boolean")
        return allowed

    def converse_structured(self, **kwargs):
        self._call("model")
        self.model_input = json.loads(kwargs["user_content"])
        self.model_response = deepcopy(self.transcript["model_response"])
        return self.model_response


def replay_case(case: dict, transcript: dict, work: Path) -> dict:
    services = RecordedServices(transcript)
    artifact = {
        "case": case["id"],
        "mode": "free-local-contract-replay",
        "paid_calls": 0,
        "deployment_validated": False,
        "semantic_review": semantic_review(case["id"], load_semantic_oracle()),
        "semantic_verdict": "not_scored",
        "attempt_outcome": "failed",
        "contract_passed": False,
    }
    try:
        review_id = f"replay-{case['id']}"
        fixture = run_fixture(
            case["fixture"], "rules", work, case["brief"], review_id=review_id
        )
        initial = {
            "review_id": review_id,
            "workload_brief": case["brief"],
            "baseline_answers": transcript.get("baseline_answers", {}),
            "retrieval_query": transcript.get("retrieval_query", case["brief"]),
            "rule_findings": fixture.findings,
            "terraform_resources": fixture.summary,
            "embedding_client": services,
            "vectors_client": services,
            "guardrails_client": services,
            "reasoning_client": services,
            "lexical_corpus_index": transcript.get("lexical_corpus_index", {}),
            "corpus_version": transcript.get("corpus_version", "unknown"),
            "max_tokens": 8192,
        }
        result = compiled_graph().invoke(initial)
        artifact["preflight_fields"] = result.get("preflight_fields", {})
        if result.get("needs_clarification"):
            artifact.update(
                attempt_outcome="needs_clarification",
                needs_clarification=result["needs_clarification"],
            )
            return artifact
        candidates = result["reasoned_findings"]
        valid, rejected = validate_findings(candidates)
        quality = build_analysis_quality(
            result.get("model_output_counts"),
            candidates,
            [finding.model_dump(mode="json") for finding in valid],
        )
        ledger = assemble_evidence_ledger(
            initial["review_id"],
            valid,
            case["brief"],
            assemble_baseline_answers(
                result.get("preflight_fields", {}), result.get("defaults_version")
            ),
            fixture.summary,
        )
        ledger["analysis_quality"] = quality
        ledger["architecture"] = place_findings(fixture.graph, valid)
        artifact.update(
            attempt_outcome="returned",
            contract_passed=not rejected and not result.get("dropped_model_findings"),
            model_verification_rejections=result.get("dropped_model_findings", []),
            schema_rejections=rejected,
            retrieved_chunks=result.get("retrieved_chunks", []),
            ledger=ledger,
            report=build_review_report(
                {"reviewId": initial["review_id"], "terraformRepoRef": case["fixture"]},
                ledger,
            ),
        )
    except Exception as exc:  # noqa: BLE001 - retain failure without echoing submitted error text
        artifact["error_kind"] = type(exc).__name__
    finally:
        artifact["replayed_operations"] = services.calls
        artifact["screened_input"] = services.screened_input
        artifact["model_input"] = services.model_input
        artifact["raw_model_response"] = services.model_response
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--case", required=True)
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    case = next(
        (case for case in load_answer_key()["cases"] if case["id"] == args.case), None
    )
    if case is None:
        parser.error("unknown frozen case ID")
    transcript = json.loads(args.transcript.read_text(encoding="utf-8"))
    if not isinstance(transcript, dict):
        parser.error("transcript must be an object")
    # Reserve a fresh output before processing; never overwrite an earlier run.
    with args.out.open("x", encoding="utf-8") as output:
        with tempfile.TemporaryDirectory(prefix="archibrief-replay-") as directory:
            result = replay_case(case, transcript, Path(directory))
        json.dump(result, output, indent=2, default=str)
        output.write("\n")
    print(
        json.dumps(
            {
                "case": args.case,
                "attempt_outcome": result["attempt_outcome"],
                "contract_passed": result["contract_passed"],
                "paid_calls": 0,
            }
        )
    )
    return 0 if result["contract_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
