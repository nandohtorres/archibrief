import json

import pytest

from backend.agent.nodes.retrieve import topic_queries
from tests.backend.adversarial.harness import load_answer_key
from tests.backend.adversarial.replay_review import replay_case
from tests.backend.agent.nodes.test_reason import _chunk, _valid_finding_item


@pytest.fixture
def case():
    return next(c for c in load_answer_key()["cases"] if c["id"] == "F06-dangerous")


@pytest.fixture
def transcript():
    return {
        "baseline_answers": {
            "regulatory_data_residency": "No special restrictions; synthetic test answer."
        },
        "vector_matches": [
            {
                "metadata": _chunk(
                    "chunk-a",
                    "Encrypt data at rest using AWS KMS customer managed keys.",
                )
            }
        ],
        "guardrail_allowed": True,
        "model_response": {"findings": [_valid_finding_item()]},
    }


def test_replay_uses_real_graph_merging_schema_quality_and_report(
    case, transcript, tmp_path
):
    result = replay_case(case, transcript, tmp_path)
    assert result["contract_passed"] is True, result.get("error_kind")
    operations = result["replayed_operations"]
    topics = topic_queries(result["model_input"]["terraform_resources"])
    assert topics, "the fixture declares resources with topic searches"
    assert operations == ["embedding", "vectors"] * (1 + len(topics)) + ["guardrail", "model"]
    assert result["paid_calls"] == 0
    assert result["deployment_validated"] is False
    assert result["semantic_verdict"] == "not_scored"
    assert (
        transcript["baseline_answers"]["regulatory_data_residency"]
        in result["screened_input"]
    )
    assert (
        result["model_input"]["terraform_resources"]
        == result["ledger"]["terraform_resources"]
    )
    findings = result["ledger"]["findings"]
    assert any(f["type"] == "deterministic-rule-result" for f in findings)
    assert any(f["model_id"] == "offline-recorded-response" for f in findings)
    assert {f["review_id"] for f in findings} == {"replay-F06-dangerous"}
    assert result["report"]["analysis_quality"]["model_verification"] == {
        "attempted": 1,
        "accepted": 1,
        "rejected": 0,
    }
    assert result["report"]["architecture"]
    assert result["report"]["baseline_answers"]


def test_missing_regulatory_answer_no_longer_pauses_the_review(
    case, transcript, tmp_path
):
    transcript["baseline_answers"] = {}
    result = replay_case(case, transcript, tmp_path)
    assert result["attempt_outcome"] != "needs_clarification"
    assert "model" in result["replayed_operations"]


def test_guardrail_block_prevents_model_dispatch(case, transcript, tmp_path):
    transcript["guardrail_allowed"] = False
    result = replay_case(case, transcript, tmp_path)
    assert result["error_kind"] == "GuardrailBlocked"
    assert "model" not in result["replayed_operations"]


@pytest.mark.parametrize("raw", [{}, {"findings": None}, {"findings": "malformed"}])
def test_malformed_model_response_is_preserved_without_claiming_completion(
    case, transcript, tmp_path, raw
):
    transcript["model_response"] = raw
    result = replay_case(case, transcript, tmp_path)
    assert result["error_kind"] == "ToolCallMissing"
    assert result["raw_model_response"] == raw
    assert result["contract_passed"] is False
    assert "report" not in result


def test_rejected_model_output_remains_in_artifact_and_rules_survive(
    case, transcript, tmp_path
):
    raw = _valid_finding_item(chunk_id="invented-chunk")
    transcript["model_response"]["findings"] = [raw]
    result = replay_case(case, transcript, tmp_path)
    assert result["attempt_outcome"] == "returned"
    assert result["contract_passed"] is False
    assert result["raw_model_response"]["findings"] == [raw]
    assert result["model_verification_rejections"]
    assert result["report"]["analysis_quality"]["outcome"] == "rules-only"
    assert result["report"]["analysis_quality"]["model_verification"]["rejected"] == 1
    assert result["ledger"]["findings"]


def test_partial_batch_keeps_valid_model_findings(case, transcript, tmp_path):
    transcript["model_response"]["findings"].append({"type": "invalid"})
    result = replay_case(case, transcript, tmp_path)
    assert result["contract_passed"] is False
    assert result["report"]["analysis_quality"]["outcome"] == "partial"
    assert result["report"]["analysis_quality"]["model_verification"]["accepted"] == 1


def test_cli_writes_private_artifact_and_sanitized_console(
    case, transcript, tmp_path, monkeypatch, capsys
):
    from tests.backend.adversarial import replay_review as runner

    source = tmp_path / "recording.json"
    source.write_text(json.dumps(transcript), encoding="utf-8")
    output = tmp_path / "result.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "replay",
            "--case",
            case["id"],
            "--transcript",
            str(source),
            "--out",
            str(output),
        ],
    )
    monkeypatch.setattr(
        runner.tempfile, "TemporaryDirectory", lambda **kw: _Work(tmp_path / "work")
    )
    assert runner.main() == 0
    assert json.loads(output.read_text())["contract_passed"] is True
    console = json.loads(capsys.readouterr().out)
    assert console["paid_calls"] == 0
    assert "raw_model_response" not in console
    with pytest.raises(FileExistsError):
        runner.main()


class _Work:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        return str(self.path)

    def __exit__(self, *args):
        return False
