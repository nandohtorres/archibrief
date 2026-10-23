import json

import pytest

from backend.agent import validate_reasoning_eval as reasoning
from backend.chat import chat_eval as chat


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
