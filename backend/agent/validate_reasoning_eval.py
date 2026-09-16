"""Run the reasoning-quality eval (backend/agent/reasoning_eval.py) against
real Bedrock.

Sibling to backend/agent/validate_reason_node.py and
backend/corpus/validate_retrieval.py — same convention: not a pytest test,
run directly with real AWS credentials. UNLIKE validate_retrieval.py, this
is NOT near-zero cost: it runs a full retrieve_node + reason_node pass
(one embed call, one vector query, one Claude Converse tool-use call, one
ApplyGuardrail call) PER BRIEF across both EVAL_BRIEFS and HOLDOUT_BRIEFS
(6 briefs total as of authoring) — do not run this casually, and per this
project's standing rule, never run it without Fernando's explicit
go-ahead in that specific moment (see Work-Project-Issues-Log.md's
2026-09-16 entries — this rule was established the hard way after an
earlier unrequested re-run in this same project).

Scores EVAL_BRIEFS and HOLDOUT_BRIEFS separately (never merged into one
number), matching backend/corpus/validate_retrieval.py's dev/held-out
separation for the same reason: keeping them separate is the entire point
of having two sets.
"""

from __future__ import annotations

import json
import os
import uuid

from backend.agent.nodes.reason import (
    FindingValidationError,
    call_reasoning_model,
    parse_model_findings,
)
from backend.agent.nodes.retrieve import retrieve_node
from backend.agent.reasoning_eval import EVAL_BRIEFS, HOLDOUT_BRIEFS, ReasoningEvalBrief, score_reasoning
from backend.corpus.lexical_index import build_lexical_corpus_index_from_disk
from backend.shared.clients import (
    BedrockEmbeddingClient,
    BedrockReasoningClient,
    GuardrailsClient,
    S3VectorsClient,
)

_VECTOR_BUCKET_NAME = os.environ.get("ARCHIBRIEF_VECTOR_BUCKET", "archibrief-dev-kb")
_VECTOR_INDEX_NAME = os.environ.get("ARCHIBRIEF_VECTOR_INDEX", "archibrief-dev-kb-index")
_REGION = os.environ.get("AWS_REGION", "us-east-1")

_GUARDRAIL_ID = os.environ.get("ARCHIBRIEF_GUARDRAIL_ID", "")
_GUARDRAIL_VERSION = os.environ.get("ARCHIBRIEF_GUARDRAIL_VERSION", "1")

# Same temporary placeholder as validate_reason_node.py, same revert
# instructions — kept in exact sync deliberately so both scripts are
# always testing the same model. See that file's comment for the full
# access-blocker history; not re-duplicated here beyond what's needed to
# know this is intentional, not copy-paste drift.
_MODEL_ID = os.environ.get("ARCHIBRIEF_REASONING_MODEL_ID", "us.anthropic.claude-sonnet-4-6")

# Same as validate_reason_node.py's reasoning: forced tool-use output is
# more verbose than free-text JSON, and a brief with 3 expected findings
# plus alternatives/framework_mapping per finding can plausibly exceed
# 4096 — use the same budget that fixed the real max_tokens truncation
# found 2026-09-16.
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
    )

    try:
        model_findings = parse_model_findings(
            raw_findings=raw_findings,
            review_id=f"reasoning-eval-{brief.brief_id}",
            model_id=reasoning_client.model_id,
            corpus_version=corpus_version,
            retrieved_chunks=retrieved_chunks,
            deterministic_rule_version=None,
        )
    except FindingValidationError as exc:
        return {
            "brief_id": brief.brief_id,
            "finding_validation_failed": True,
            "failures": exc.failures,
        }

    result = score_reasoning(model_findings, brief)
    result["retrieved_chunk_count"] = len(retrieved_chunks)
    result["raw_model_finding_count"] = len(raw_findings)
    return result


def _print_report(label: str, results: list[dict]) -> None:
    print(f"=== {label} ===")
    scored = [r for r in results if "topic_recall" in r]
    if scored:
        overall = sum(r["topics_covered"] for r in scored) / sum(r["topics_total"] for r in scored)
        print(f"Overall topic recall: {overall:.0%} "
              f"({sum(r['topics_covered'] for r in scored)}/{sum(r['topics_total'] for r in scored)})\n")
    for r in results:
        print(f"--- {r['brief_id']} ---")
        if r.get("blocked_by_guardrails"):
            print("  BLOCKED by guardrails")
            continue
        if r.get("finding_validation_failed"):
            print("  FINDING VALIDATION FAILED:")
            for f in r["failures"]:
                print(f"    - {f}")
            continue
        print(f"  topic recall: {r['topic_recall']:.0%} ({r['topics_covered']}/{r['topics_total']})")
        for hit in r["topic_hits"]:
            status = "OK  " if hit["covered"] else "MISS"
            flag = ""
            if hit["citation_from_plausible_source"] is False:
                flag = "  [citation from an unexpected document — review]"
            print(f"    {status} {hit['topic_id']}: {hit['description']}{flag}")
        if r["unmatched_findings"]:
            print("  unmatched findings (not necessarily wrong — review):")
            for uf in r["unmatched_findings"]:
                print(f"    - [{uf['category']}] {uf['finding']}")
    print()


def main() -> None:
    embedding_client = BedrockEmbeddingClient(region_name=_REGION)
    vectors_client = S3VectorsClient(
        bucket_name=_VECTOR_BUCKET_NAME, index_name=_VECTOR_INDEX_NAME, region_name=_REGION
    )
    lexical_corpus_index = build_lexical_corpus_index_from_disk()
    guardrails_client = GuardrailsClient(
        guardrail_id=_GUARDRAIL_ID, guardrail_version=_GUARDRAIL_VERSION, region_name=_REGION
    )
    reasoning_client = BedrockReasoningClient(model_id=_MODEL_ID, region_name=_REGION)

    dev_results = [
        _run_brief(b, embedding_client, vectors_client, lexical_corpus_index, guardrails_client, reasoning_client)
        for b in EVAL_BRIEFS
    ]
    _print_report("Dev set (EVAL_BRIEFS)", dev_results)

    holdout_results = [
        _run_brief(b, embedding_client, vectors_client, lexical_corpus_index, guardrails_client, reasoning_client)
        for b in HOLDOUT_BRIEFS
    ]
    _print_report("Held-out set (HOLDOUT_BRIEFS)", holdout_results)

    print(json.dumps({"dev": dev_results, "holdout": holdout_results}, indent=2, default=str))


if __name__ == "__main__":
    main()
