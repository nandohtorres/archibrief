import json

import pytest

from backend.agent import validate_reason_node as component
from backend.agent import validate_reasoning_eval as reasoning
from backend.chat import chat_eval as chat
from backend.corpus import validate_retrieval as retrieval
from backend.corpus import validate_retrieve_node as merged

ALL_RUNNERS = [reasoning, chat, component, retrieval, merged]


@pytest.mark.parametrize("runner", [reasoning, chat])
def test_plan_never_constructs_an_aws_client(runner, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("offline plan attempted to construct an AWS client")

    for name in (
        "BedrockEmbeddingClient",
        "BedrockReasoningClient",
        "GuardrailsClient",
        "S3VectorsClient",
    ):
        monkeypatch.setattr(runner, name, forbidden)
    monkeypatch.setattr("sys.argv", ["eval", "--plan", "--traps", "--limit", "1"])
    runner.main()
    plan = json.loads(capsys.readouterr().out)
    assert plan["partial"] is True
    assert all(len(cases) == 1 for cases in plan["case_ids"].values())


@pytest.mark.parametrize("runner", [reasoning, chat])
def test_paid_runs_require_confirmation_before_clients(runner, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("unconfirmed evaluation constructed an AWS client")

    monkeypatch.setattr(runner, "BedrockEmbeddingClient", forbidden)
    monkeypatch.setattr("sys.argv", ["eval"])
    if runner is reasoning:
        with pytest.raises(SystemExit) as error:
            runner.main()
        assert error.value.code == 2
    else:
        assert runner.main() == 2


@pytest.mark.parametrize("runner", [reasoning, chat])
def test_nonpositive_limits_fail_even_in_preview(runner, monkeypatch):
    monkeypatch.setattr("sys.argv", ["eval", "--plan", "--limit", "0"])
    with pytest.raises(SystemExit) as error:
        runner.main()
    assert error.value.code == 2


@pytest.mark.parametrize("runner", [component, retrieval, merged])
def test_legacy_validation_previews_never_construct_clients(
    runner, monkeypatch, capsys
):
    def forbidden(*args, **kwargs):
        pytest.fail("preview constructed a chargeable client")

    for name in (
        "BedrockEmbeddingClient",
        "BedrockReasoningClient",
        "GuardrailsClient",
        "S3VectorsClient",
    ):
        if hasattr(runner, name):
            monkeypatch.setattr(runner, name, forbidden)
    monkeypatch.setattr("sys.argv", ["eval", "--plan"])
    runner.main()
    plan = json.loads(capsys.readouterr().out)
    assert plan["case_ids"]
    assert plan["admission"]["planned_service_calls_upper_bound"] > 0
    assert plan["admission"]["monetary_limit_enforced"] is False


@pytest.mark.parametrize("runner", ALL_RUNNERS)
@pytest.mark.parametrize(
    "options", [[], ["--confirm-paid"], ["--confirm-paid", "--max-paid-calls", "1"]]
)
def test_every_entrypoint_rejects_unconfirmed_or_unbudgeted_scope_before_clients(
    runner, options, monkeypatch
):
    def forbidden(*args, **kwargs):
        pytest.fail("denied scope constructed an AWS client")

    monkeypatch.setattr(runner, "BedrockEmbeddingClient", forbidden)
    monkeypatch.setattr("sys.argv", ["eval", *options])
    if runner is chat and not options:
        assert runner.main() == 2
    else:
        with pytest.raises(SystemExit) as error:
            runner.main()
        assert error.value.code == 2


def test_reasoning_failure_does_not_erase_later_scheduled_cases(monkeypatch, tmp_path):
    for name in (
        "BedrockEmbeddingClient",
        "BedrockReasoningClient",
        "GuardrailsClient",
        "S3VectorsClient",
    ):
        monkeypatch.setattr(reasoning, name, lambda **kwargs: None)
    monkeypatch.setattr(reasoning, "build_lexical_corpus_index_from_disk", dict)
    seen = []

    def run(brief, *args):
        seen.append(brief.brief_id)
        if len(seen) == 1:
            raise RuntimeError("PRIVATE-CANARY")
        return reasoning.score_reasoning([], brief)

    monkeypatch.setattr(reasoning, "_run_brief", run)
    output = tmp_path / "results.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "eval",
            "--confirm-paid",
            "--max-paid-calls",
            "100",
            "--run-log",
            str(tmp_path / "calls.json"),
            "--out",
            str(output),
        ],
    )
    assert reasoning.main() == 1
    result = json.loads(output.read_text())
    assert len(result["dev"]) + len(result["holdout"]) == len(seen) == 6
    assert result["dev"][0]["attempt_outcome"] == "failed"
    assert "PRIVATE-CANARY" not in output.read_text()


def test_reasoning_trap_failure_returns_nonzero_without_hiding_the_score(
    monkeypatch, tmp_path
):
    for name in (
        "BedrockEmbeddingClient",
        "BedrockReasoningClient",
        "GuardrailsClient",
        "S3VectorsClient",
    ):
        monkeypatch.setattr(reasoning, name, lambda **kwargs: None)
    monkeypatch.setattr(reasoning, "build_lexical_corpus_index_from_disk", dict)
    monkeypatch.setattr(
        reasoning,
        "_run_brief",
        lambda brief, *args: reasoning.score_reasoning([], brief),
    )
    output = tmp_path / "traps.json"
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
    assert reasoning.main() == 1
    assert json.loads(output.read_text())["traps"][0]["trap_passed"] is False
