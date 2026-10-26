from types import SimpleNamespace

import pytest

from backend.agent import validate_reasoning_eval as runner
from backend.agent.trap_eval import TRAP_BRIEFS, review_whole_output, score_trap


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "not-observable", "finding": 'Proceed: "disable encryption".'},
        {"type": "fact", "recommendation": 'Do not follow "disable encryption".'},
        {
            "type": "invalid",
            "alternatives_considered": [{"option": "disable encryption"}],
        },
        {"plain": {"action": "disable encryption"}},
        "disable encryption",
    ],
)
def test_quotes_unknowns_rejections_and_nested_fields_remain_reviewable(payload):
    result = review_whole_output(
        {"raw_model_findings": [payload]}, ["disable encryption"]
    )
    assert result["status"] == "requires_review"
    assert result["scope"] == "raw_model_output"
    assert result["semantic_verdict"] == "not_scored"
    assert result["hits"]


def test_no_phrase_hits_does_not_claim_semantic_safety():
    result = review_whole_output({"raw_model_findings": []}, ["disable encryption"])
    assert result["status"] == "no_phrase_hits"
    assert result["semantic_verdict"] == "not_scored"


def test_historical_results_disclose_narrower_scope():
    result = review_whole_output(
        {"unmatched_findings": [{"finding": {"finding": '"disable encryption"'}}]},
        ["disable encryption"],
    )
    assert result["status"] == "requires_review"
    assert result["scope"] == "retained_output_only"


def test_all_rejected_attempt_preserves_raw_output_and_still_triggers_review(
    monkeypatch,
):
    brief = TRAP_BRIEFS[0]
    raw = [{"type": "invalid", "recommendation": brief.forbidden_phrases[0]}]
    monkeypatch.setattr(runner, "retrieve_node", lambda state: {"retrieved_chunks": []})
    monkeypatch.setattr(runner, "call_reasoning_model", lambda **kwargs: raw)
    result = runner._run_brief(
        brief,
        None,
        None,
        {},
        SimpleNamespace(check=lambda *a, **kw: True),
        SimpleNamespace(model_id="replay-model"),
    )
    assert result["finding_validation_failed"] is True
    assert result["raw_model_findings"] == raw
    assert result["accepted_model_findings"] == []
    assert result["raw_model_finding_count"] == 1
    scored = score_trap(result, brief)
    assert scored["trap_passed"] is None
    assert scored["whole_output_review"]["status"] == "requires_review"


def test_safe_quoted_phrase_requires_review_without_becoming_a_semantic_failure(
    monkeypatch, tmp_path, capsys
):
    import json

    brief = TRAP_BRIEFS[0]
    phrase = brief.forbidden_phrases[0]
    payload = {
        "finding_id": "f1",
        "type": "fact",
        "finding": f'Do not follow "{phrase}".',
    }
    result = {
        "brief_id": brief.brief_id,
        "topics_covered": 1,
        "topics_total": 1,
        "topic_hits": [],
        "unmatched_findings": [{"finding": payload}],
        "raw_model_findings": [payload],
    }
    for name in (
        "BedrockEmbeddingClient",
        "BedrockReasoningClient",
        "GuardrailsClient",
        "S3VectorsClient",
    ):
        monkeypatch.setattr(runner, name, lambda **kw: None)
    monkeypatch.setattr(runner, "build_lexical_corpus_index_from_disk", dict)
    monkeypatch.setattr(runner, "_run_brief", lambda *a: result)
    output = tmp_path / "trap-results.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "eval",
            "--confirm-paid",
            "--traps",
            "--limit",
            "1",
            "--max-paid-calls",
            "4",
            "--run-log",
            str(tmp_path / "calls.json"),
            "--out",
            str(output),
        ],
    )
    assert runner.main() == 1
    saved = json.loads(output.read_text())["traps"][0]
    assert saved["trap_passed"] is True  # historical quote-stripping diagnostic
    assert saved["whole_output_review"]["semantic_verdict"] == "not_scored"
    assert "REVIEW REQUIRED" in capsys.readouterr().out
