import json
from types import SimpleNamespace

import pytest

from tests.backend.adversarial import evaluate_review as runner
from tests.backend.agent.nodes.test_reason import _chunk, _valid_finding_item


def test_integrated_preview_never_constructs_clients(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("preview constructed an AWS client")

    for name in (
        "BedrockEmbeddingClient",
        "BedrockReasoningClient",
        "GuardrailsClient",
        "S3VectorsClient",
    ):
        monkeypatch.setattr(runner, name, forbidden)
    monkeypatch.setattr("sys.argv", ["eval", "--plan", "--case", "F06-dangerous"])
    assert runner.main() == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["admission"]["planned_service_calls_upper_bound"] == 5
    assert plan["required_baseline_fields"] == {
        "F06-dangerous": ["regulatory_data_residency"]
    }
    assert plan["deployment_validated"] is False
    assert plan["semantic_verdict"] == "not_scored"


def test_missing_baselines_cannot_spend_a_guardrail_call(monkeypatch, tmp_path):
    monkeypatch.setattr(
        runner, "GuardrailsClient", lambda *a, **kw: pytest.fail("constructed guard")
    )
    output = tmp_path / "results.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "eval",
            "--case",
            "F06-dangerous",
            "--scanner",
            "rules",
            "--confirm-paid",
            "--max-paid-calls",
            "5",
            "--out",
            str(output),
        ],
    )
    with pytest.raises(SystemExit) as error:
        runner.main()
    assert error.value.code == 2
    assert not output.exists()


def test_integrated_fake_service_run_retains_failed_and_successful_cases(
    monkeypatch, tmp_path
):
    from tests.backend.adversarial.test_replay_review import _Work

    answer_file = tmp_path / "answers.json"
    ids = ["F06-dangerous", "F07-dangerous"]
    answer_file.write_text(
        json.dumps(
            {
                case: {"regulatory_data_residency": "Synthetic test answer"}
                for case in ids
            }
        ),
        encoding="utf-8",
    )
    chunk = _chunk(
        "chunk-a", "Encrypt data at rest using AWS KMS customer managed keys."
    )
    calls = []

    def model(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("PRIVATE-ERROR-CANARY")
        return {"findings": [_valid_finding_item()]}

    monkeypatch.setattr(
        runner,
        "BedrockEmbeddingClient",
        lambda **kw: SimpleNamespace(embed=lambda text: [0.0]),
    )
    monkeypatch.setattr(
        runner,
        "S3VectorsClient",
        lambda **kw: SimpleNamespace(
            query_vectors=lambda **kwargs: [{"metadata": chunk}]
        ),
    )
    monkeypatch.setattr(
        runner,
        "GuardrailsClient",
        lambda *a, **kw: SimpleNamespace(check=lambda *a, **kw: True),
    )
    monkeypatch.setattr(
        runner,
        "BedrockReasoningClient",
        lambda **kw: SimpleNamespace(converse_structured=model),
    )
    monkeypatch.setattr(runner, "build_lexical_corpus_index_from_disk", dict)
    folders = []

    def temporary(**kwargs):
        folders.append(tmp_path / f"case-{len(folders)}")
        return _Work(folders[-1])

    monkeypatch.setattr(runner.tempfile, "TemporaryDirectory", temporary)
    output, journal = tmp_path / "results.json", tmp_path / "calls.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "eval",
            "--case",
            ids[0],
            "--case",
            ids[1],
            "--scanner",
            "rules",
            "--baseline-answers",
            str(answer_file),
            "--confirm-paid",
            "--max-paid-calls",
            "10",
            "--run-log",
            str(journal),
            "--out",
            str(output),
        ],
    )
    assert runner.main() == 1
    result = json.loads(output.read_text())
    assert [case["attempt_outcome"] for case in result["attempts"]] == [
        "failed",
        "returned",
    ]
    delivered = result["attempts"][1]
    assert delivered["contract_passed"] is True
    assert delivered["service_operations"] == [
        "guardrail",
        "embedding",
        "vectors",
        "guardrail",
        "model",
    ]
    assert delivered["audit_persisted"] is False
    assert (
        delivered["audit_entry"]["deterministicRuleVersion"] == "rule_engine@2026-10-23"
    )
    assert delivered["report"]["analysis_scope"]
    assert delivered["semantic_verdict"] == "not_scored"
    assert len(json.loads(journal.read_text())["calls"]) == 10
    assert "PRIVATE-ERROR" not in output.read_text()
