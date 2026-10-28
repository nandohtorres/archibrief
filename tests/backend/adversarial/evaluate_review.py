"""Guarded paid evaluation through local production graph/report functions.

--plan is offline. Actual execution additionally requires explicit operator
authorization, --confirm-paid, call/output limits and a fresh private --out.
This does not deploy or exercise API Gateway/AgentCore transport or persistence.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import uuid
from pathlib import Path

from backend.agent.nodes.retrieve import MAX_RETRIEVAL_CALLS
from backend.corpus.lexical_index import build_lexical_corpus_index_from_disk
from backend.shared.baseline import SUBMISSION_REQUIRED_FIELDS
from backend.shared.clients import (
    BedrockEmbeddingClient,
    BedrockReasoningClient,
    GuardrailsClient,
    S3VectorsClient,
)
from backend.shared.evaluation_budget import (
    EvaluationLimitReached,
    add_budget_options,
    admit_budget,
    budget_plan,
)
from backend.shared.evaluation_manifest import attach_manifest
from tests.backend.adversarial.harness import load_answer_key, trivy_path


class MeteredServices:
    def __init__(self, args, budget):
        self.args, self.budget = args, budget
        self.model_id = args.model
        self.calls = []
        self.screened_input = None
        self.model_input = None
        self.model_response = None
        self.guardrails_decisions = []
        self.clients = {}

    def client(self, kind):
        if self.budget.stop_reason:
            raise EvaluationLimitReached(self.budget.stop_reason)
        if kind not in self.clients:
            shared = {
                "region_name": self.args.region,
                "no_retries": True,
                "read_timeout_seconds": 30,
            }
            if kind == "embedding":
                client = BedrockEmbeddingClient(**shared)
            elif kind == "vectors":
                client = S3VectorsClient(
                    bucket_name=self.args.vector_bucket,
                    index_name=self.args.vector_index,
                    **shared,
                )
            elif kind == "guardrails":
                client = GuardrailsClient(
                    self.args.guardrail_id, self.args.guardrail_version, **shared
                )
            else:
                client = BedrockReasoningClient(
                    model_id=self.model_id, **{**shared, "read_timeout_seconds": 60}
                )
            self.clients[kind] = self.budget.wrap(client, kind)
        return self.clients[kind]

    def embed(self, text):
        self.calls.append("embedding")
        return self.client("embedding").embed(text)

    def query_vectors(self, **kwargs):
        self.calls.append("vectors")
        return self.client("vectors").query_vectors(**kwargs)

    def check(self, text, **kwargs):
        self.calls.append("guardrail")
        self.screened_input = text
        allowed = self.client("guardrails").check(text, **kwargs)
        self.guardrails_decisions.append(
            {
                "stage": "reason_input"
                if "embedding" in self.calls
                else "ingest_input",
                "allowed": allowed,
            }
        )
        return allowed

    def converse_structured(self, **kwargs):
        self.calls.append("model")
        self.model_input = json.loads(kwargs["user_content"])
        self.model_response = self.client("reasoning").converse_structured(**kwargs)
        return self.model_response


def _save(path, artifact):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("x", encoding="utf-8") as output:
        json.dump(artifact, output, indent=2, default=str)
        output.write("\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--confirm-paid", action="store_true")
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--scanner", choices=("rules", "trivy"), default="trivy")
    parser.add_argument(
        "--baseline-answers",
        type=Path,
        help="private case-ID to baseline-answer object",
    )
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--model",
        default=os.environ.get(
            "ARCHIBRIEF_REASONING_MODEL_ID", "us.anthropic.claude-sonnet-4-6"
        ),
    )
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    parser.add_argument(
        "--guardrail-id", default=os.environ.get("ARCHIBRIEF_GUARDRAIL_ID", "")
    )
    parser.add_argument(
        "--guardrail-version",
        default=os.environ.get("ARCHIBRIEF_GUARDRAIL_VERSION", "1"),
    )
    parser.add_argument(
        "--vector-bucket",
        default=os.environ.get("ARCHIBRIEF_VECTOR_BUCKET", "archibrief-dev-kb"),
    )
    parser.add_argument(
        "--vector-index",
        default=os.environ.get("ARCHIBRIEF_VECTOR_INDEX", "archibrief-dev-kb-index"),
    )
    add_budget_options(parser)
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    key = load_answer_key()
    requested = set(args.case_ids or [case["id"] for case in key["cases"]])
    if requested - {case["id"] for case in key["cases"]} or (
        args.case_ids and len(requested) != len(args.case_ids)
    ):
        parser.error("case IDs must be known and unique")
    cases = [case for case in key["cases"] if case["id"] in requested][: args.limit]
    answers = (
        json.loads(args.baseline_answers.read_text(encoding="utf-8"))
        if args.baseline_answers
        else {}
    )
    if not isinstance(answers, dict) or any(
        not isinstance(value, dict) for value in answers.values()
    ):
        parser.error("baseline answers must map case IDs to answer objects")
    for values in answers.values():
        if not all(
            isinstance(value, str) and 0 < len(value) <= 1000
            for value in values.values()
        ):
            parser.error("baseline answer values must be nonempty bounded strings")
    selected = [
        {**case, "evaluation_baseline_answers": answers.get(case["id"], {})}
        for case in cases
    ]
    # The same answers the live submission form requires (submit_review).
    missing = {
        case["id"]: [
            name
            for name in SUBMISSION_REQUIRED_FIELDS
            if not answers.get(case["id"], {}).get(name)
        ]
        for case in cases
    }
    missing = {name: fields for name, fields in missing.items() if fields}
    attach_manifest(
        args,
        {"frozen_adversarial": selected},
        {
            "model": args.model,
            "region": args.region,
            "vector_bucket": args.vector_bucket,
            "vector_index": args.vector_index,
            "guardrail_id": args.guardrail_id,
            "guardrail_version": args.guardrail_version,
            "scanner": args.scanner,
            "max_output_tokens": 8192,
        },
    )
    # Ingest and reasoning Guardrails checks, retrieval and one model call.
    calls = (MAX_RETRIEVAL_CALLS + 3) * len(cases)
    metadata = {
        "mode": "integrated-local-application-evaluation",
        "partial": bool(
            args.limit
            or args.case_ids
            or args.scanner == "rules"
            or not args.guardrail_id
            or not args.evaluation_manifest["local_corpus_available"]
        ),
        "case_ids": {"frozen_adversarial": [case["id"] for case in cases]},
        "admission": budget_plan(args, parser, calls),
        "deployment_validated": False,
        "semantic_verdict": "not_scored",
        "guardrail_configured": bool(args.guardrail_id),
        "local_lexical_corpus_available": args.evaluation_manifest[
            "local_corpus_available"
        ],
        "required_baseline_fields": missing,
    }
    if args.plan:
        print(json.dumps(metadata, indent=2))
        return 0
    if not args.confirm_paid:
        parser.error(
            "paid execution requires --confirm-paid and explicit operator authorization"
        )
    if missing:
        parser.error(
            "required baseline answers are missing; inspect --plan for the fields each case needs"
        )
    if args.out is None or args.out.exists():
        parser.error("paid execution requires a fresh private --out path")
    if args.scanner == "trivy" and trivy_path() is None:
        parser.error(
            "local Trivy is unavailable; --scanner rules is a partial diagnostic"
        )
    budget = admit_budget(args, parser, calls)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8"):
        pass
    artifact = {
        "metadata": metadata,
        "attempts": [
            {
                "case": case["id"],
                "attempt_outcome": "not_started",
                "contract_passed": False,
            }
            for case in cases
        ],
        "call_journal": str(budget.path),
    }
    _save(args.out, artifact)
    try:
        from tests.backend.adversarial.replay_review import replay_case

        lexical = build_lexical_corpus_index_from_disk()
    except Exception as error:  # noqa: BLE001 - retain scheduled cases without leaking error text
        artifact["setup_error_kind"] = type(error).__name__
        artifact["admission"] = budget.summary()
        for attempt in artifact["attempts"]:
            attempt["attempt_outcome"] = "not_run"
        _save(args.out, artifact)
        print(
            json.dumps(
                {"setup_error_kind": type(error).__name__, "attempts": len(cases)}
            )
        )
        return 1
    for index, case in enumerate(cases):
        before = len(budget.calls)
        try:
            with tempfile.TemporaryDirectory(
                prefix="archibrief-integrated-eval-"
            ) as directory:
                result = replay_case(
                    case,
                    {
                        "baseline_answers": answers.get(case["id"], {}),
                        "lexical_corpus_index": lexical,
                        "screen_ingest": True,
                    },
                    Path(directory),
                    services=MeteredServices(args, budget),
                    mode=metadata["mode"],
                    scanner=args.scanner,
                )
            result["service_call_attempts"] = len(budget.calls) - before
            if result.get("error_kind") == "EvaluationLimitReached":
                result["attempt_outcome"] = (
                    "not_run" if len(budget.calls) == before else "stopped"
                )
            artifact["attempts"][index] = result
        except KeyboardInterrupt:
            artifact["attempts"][index] = {
                "case": case["id"],
                "attempt_outcome": "interrupted",
                "contract_passed": False,
            }
            artifact["admission"] = budget.summary()
            _save(args.out, artifact)
            return 130
        artifact["admission"] = budget.summary()
        _save(args.out, artifact)
    passed = all(case["contract_passed"] for case in artifact["attempts"])
    print(
        json.dumps(
            {
                "mode": metadata["mode"],
                "attempts": len(cases),
                "contract_passed": passed,
                "semantic_verdict": "not_scored",
                "private_artifact": str(args.out),
            }
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
