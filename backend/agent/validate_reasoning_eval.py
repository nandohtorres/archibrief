"""Run the reasoning-quality eval (backend/agent/reasoning_eval.py) against
real Bedrock.

Sibling to backend/agent/validate_reason_node.py and
backend/corpus/validate_retrieval.py — same convention: not a pytest test,
run directly with real AWS credentials and explicit paid admission. This
controlled component diagnostic runs retrieval and reasoning
(one embed call, one vector query, one Claude Converse tool-use call, one
ApplyGuardrail call) PER BRIEF across both EVAL_BRIEFS and HOLDOUT_BRIEFS
(6 briefs total as of authoring), so each run costs real money. Run it
deliberately, not as part of routine testing.

Scores EVAL_BRIEFS and HOLDOUT_BRIEFS separately (never merged into one
number), matching backend/corpus/validate_retrieval.py's dev/held-out
separation for the same reason: keeping them separate is the entire point
of having two sets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from backend.agent.nodes.reason import (
    call_reasoning_model,
    verify_model_findings,
)
from backend.agent.nodes.retrieve import retrieve_node
from backend.agent.reasoning_eval import (
    EVAL_BRIEFS,
    HOLDOUT_BRIEFS,
    ReasoningEvalBrief,
    score_reasoning,
)
from backend.agent.trap_eval import TRAP_BRIEFS, score_trap
from backend.corpus.lexical_index import build_lexical_corpus_index_from_disk
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

_VECTOR_BUCKET_NAME = os.environ.get("ARCHIBRIEF_VECTOR_BUCKET", "archibrief-dev-kb")
_VECTOR_INDEX_NAME = os.environ.get("ARCHIBRIEF_VECTOR_INDEX", "archibrief-dev-kb-index")
_REGION = os.environ.get("AWS_REGION", "us-east-1")

_GUARDRAIL_ID = os.environ.get("ARCHIBRIEF_GUARDRAIL_ID", "")
_GUARDRAIL_VERSION = os.environ.get("ARCHIBRIEF_GUARDRAIL_VERSION", "1")

# Same default model as runtime_entrypoint.py, so the eval tests the model
# the pipeline uses.
_MODEL_ID = os.environ.get("ARCHIBRIEF_REASONING_MODEL_ID", "us.anthropic.claude-sonnet-4-6")

# Same as validate_reason_node.py's reasoning: forced tool-use output is
# more verbose than free-text JSON, and a brief with 3 expected findings
# plus alternatives/framework_mapping per finding can plausibly exceed
# 4096, so use the same budget.
_MAX_TOKENS = 8192


def _run_brief(
    brief: ReasoningEvalBrief,
    embedding_client: BedrockEmbeddingClient,
    vectors_client: S3VectorsClient,
    lexical_corpus_index: dict,
    guardrails_client: GuardrailsClient,
    reasoning_client: BedrockReasoningClient,
) -> dict:
    retrieve_result = retrieve_node(
        {
            "retrieval_query": brief.retrieval_query,
            "embedding_client": embedding_client,
            "vectors_client": vectors_client,
            "lexical_corpus_index": lexical_corpus_index,
        }
    )
    retrieved_chunks = retrieve_result["retrieved_chunks"]

    allowed = guardrails_client.check(brief.workload_brief, source="INPUT")
    if not allowed:
        return {
            "brief_id": brief.brief_id,
            "blocked_by_guardrails": True,
        }

    corpus_version = retrieved_chunks[0]["corpus_version"] if retrieved_chunks else "unknown"
    raw_findings = call_reasoning_model(
        reasoning_client=reasoning_client,
        workload_brief=brief.workload_brief,
        rule_findings=brief.rule_findings,
        retrieved_chunks=retrieved_chunks,
        max_tokens=_MAX_TOKENS,
        terraform_resources=brief.terraform_resources,
    )

    # Same rule as the live pipeline: a finding whose citation fails is
    # dropped and the rest are scored, so one bad quote doesn't hide what
    # the model did on the rest of the brief. Every failure is still
    # reported, under dropped_findings.
    model_findings, failures = verify_model_findings(
        raw_findings=raw_findings,
        review_id=f"reasoning-eval-{brief.brief_id}",
        model_id=reasoning_client.model_id,
        corpus_version=corpus_version,
        retrieved_chunks=retrieved_chunks,
        deterministic_rule_version=None,
        terraform_resources=brief.terraform_resources,
    )
    if raw_findings and not model_findings:
        return {
            "brief_id": brief.brief_id,
            "finding_validation_failed": True,
            "failures": failures,
        }

    result = score_reasoning(model_findings, brief)
    result["retrieved_chunk_count"] = len(retrieved_chunks)
    result["raw_model_finding_count"] = len(raw_findings)
    result["dropped_findings"] = failures
    return result


def _print_report(label: str, results: list[dict]) -> None:
    print(f"=== {label} ===")
    scored = [r for r in results if "topic_recall" in r]
    blocked = [r for r in results if r.get("blocked_by_guardrails")]
    failed = [r for r in results if r.get("finding_validation_failed")]
    if scored:
        overall = sum(r["topics_covered"] for r in scored) / sum(r["topics_total"] for r in scored)
        # Say explicitly when blocked/failed briefs make the headline number
        # partial.
        completeness_note = (
            ""
            if len(scored) == len(results)
            else (
                f"  [INCOMPLETE RUN: {len(scored)}/{len(results)} briefs scored — "
                f"{len(blocked)} blocked, {len(failed)} failed validation — this "
                f"number does NOT represent the full brief set]"
            )
        )
        print(
            f"Overall topic recall: {overall:.0%} "
            f"({sum(r['topics_covered'] for r in scored)}/{sum(r['topics_total'] for r in scored)})"
            f"{completeness_note}\n"
        )
    else:
        print(f"No briefs scored ({len(blocked)} blocked, {len(failed)} failed validation)\n")
    for r in results:
        print(f"--- {r['brief_id']} ---")
        if r.get("execution_error_kind"):
            print(f"  {r['attempt_outcome']}: {r['execution_error_kind']}")
            continue
        if r.get("blocked_by_guardrails"):
            print("  BLOCKED by guardrails")
            continue
        if r.get("finding_validation_failed"):
            print("  FINDING VALIDATION FAILED:")
            for f in r["failures"]:
                print(f"    - {f}")
            continue
        print(
            f"  topic recall: {r['topic_recall']:.0%} ({r['topics_covered']}/{r['topics_total']})"
        )
        for f in r.get("dropped_findings", []):
            print(f"  dropped (citation failed): {f}")
        for hit in r["topic_hits"]:
            status = "OK  " if hit["covered"] else "MISS"
            flag = ""
            relevance = hit["citation_relevance"]
            if relevance == "implausible":
                flag = "  [citation from an unexpected document — review]"
            elif relevance == "missing":
                flag = "  [covering finding has no citation at all — review]"
            print(f"    {status} {hit['topic_id']}: {hit['description']}{flag}")
        if r["unmatched_findings"]:
            print(
                "  unmatched findings (not necessarily wrong — review, label precision_label after reading):"
            )
            for uf in r["unmatched_findings"]:
                f = uf["finding"]
                print(f"    - [{f['category']}] {f['finding']}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--confirm-paid", action="store_true")
    parser.add_argument("--plan", action="store_true", help="print case IDs without AWS clients")
    parser.add_argument("--traps", action="store_true", help="run only adversarial briefs")
    parser.add_argument(
        "--limit", type=int, help="maximum briefs per selected set; partial evaluation"
    )
    parser.add_argument("--out", type=Path, help="write structured results for review")
    add_budget_options(parser)
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    selected = (
        {"traps": TRAP_BRIEFS} if args.traps else {"dev": EVAL_BRIEFS, "holdout": HOLDOUT_BRIEFS}
    )
    selected = {name: briefs[: args.limit] for name, briefs in selected.items()}
    planned_calls = 4 * sum(len(briefs) for briefs in selected.values())
    metadata = {
        "model": _MODEL_ID,
        "partial": args.limit is not None,
        "max_output_tokens_per_brief": _MAX_TOKENS,
        "case_ids": {
            name: [brief.brief_id for brief in briefs] for name, briefs in selected.items()
        },
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "mode": "controlled-model-component",
        "admission": budget_plan(args, parser, planned_calls),
    }
    if args.plan:
        print(json.dumps(metadata, indent=2))
        return 0
    if not args.confirm_paid:
        parser.error(
            "paid AWS evaluation requires --confirm-paid and explicit operator authorization"
        )
    budget = admit_budget(args, parser, planned_calls)

    def publish(result):
        artifact = {
            "metadata": metadata,
            "admission": budget.summary(),
            "call_journal": str(budget.path),
            **result,
        }
        if args.out:
            args.out.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")
        print(json.dumps(artifact, indent=2, default=str))

    embedding_client = budget.wrap(
        BedrockEmbeddingClient(region_name=_REGION, no_retries=True, read_timeout_seconds=30),
        "embedding",
    )
    vectors_client = budget.wrap(
        S3VectorsClient(
            bucket_name=_VECTOR_BUCKET_NAME,
            index_name=_VECTOR_INDEX_NAME,
            region_name=_REGION,
            no_retries=True,
            read_timeout_seconds=30,
        ),
        "vectors",
    )
    lexical_corpus_index = build_lexical_corpus_index_from_disk()
    guardrails_client = budget.wrap(
        GuardrailsClient(
            guardrail_id=_GUARDRAIL_ID,
            guardrail_version=_GUARDRAIL_VERSION,
            region_name=_REGION,
            no_retries=True,
            read_timeout_seconds=30,
        ),
        "guardrails",
    )
    reasoning_client = budget.wrap(
        BedrockReasoningClient(
            model_id=_MODEL_ID, region_name=_REGION, no_retries=True, read_timeout_seconds=60
        ),
        "reasoning",
    )

    def attempt(brief):
        try:
            return {
                **_run_brief(
                    brief,
                    embedding_client,
                    vectors_client,
                    lexical_corpus_index,
                    guardrails_client,
                    reasoning_client,
                ),
                "attempt_outcome": "returned",
            }
        except Exception as exc:  # noqa: BLE001 - retain every scheduled case without leaking error content
            return {
                "brief_id": brief.brief_id,
                "finding_validation_failed": True,
                "failures": [],
                "attempt_outcome": "not_run"
                if isinstance(exc, EvaluationLimitReached)
                else "failed",
                "execution_error_kind": type(exc).__name__,
            }

    # `--traps` runs ONLY the adversarial trap set (backend/agent/trap_eval.py),
    # never mixed into the dev/held-out numbers - same separation rule.
    if args.traps:
        trap_results = [
            score_trap(
                attempt(b),
                b,
            )
            for b in selected["traps"]
        ]
        for r in trap_results:
            verdict = {True: "PASS", False: "FAIL", None: "BLOCKED/INVALID"}[r["trap_passed"]]
            print(f"{verdict:16} {r['brief_id']}: {r['trick']}")
            if r.get("forbidden_phrase_hits"):
                print(f"{'':16} took the bait: {r['forbidden_phrase_hits']}")
            if r.get("dropped_findings"):
                print(f"{'':16} {len(r['dropped_findings'])} finding(s) dropped: citation failed")
        publish({"traps": trap_results})
        return (
            1
            if any(
                r.get("execution_error_kind")
                or r.get("finding_validation_failed")
                or r.get("trap_passed") is False
                for r in trap_results
            )
            else 0
        )

    dev_results = [attempt(b) for b in selected["dev"]]
    _print_report("Dev set (EVAL_BRIEFS)", dev_results)

    holdout_results = [attempt(b) for b in selected["holdout"]]
    _print_report("Held-out set (HOLDOUT_BRIEFS)", holdout_results)

    publish({"dev": dev_results, "holdout": holdout_results})
    return (
        1
        if any(
            r.get("execution_error_kind") or r.get("finding_validation_failed")
            for r in [*dev_results, *holdout_results]
        )
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
