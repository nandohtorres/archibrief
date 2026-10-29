"""The runtime's model call must end before the workers stop waiting for
the runtime, and never fall back to botocore's 60 s default.

The call doesn't stream: Bedrock holds a forced, strict tool call's output
until it is finished, so read_timeout_seconds is the wait for the whole
answer and the worst case.

The runtime module imports the AgentCore SDK, which only ships in the
runtime package, so these checks read the source instead of importing it.
"""

import ast
from pathlib import Path

from backend.lambdas.deeper_review.worker import (
    AGENT_READ_TIMEOUT_SECONDS as DEEPER_WORKER_WAIT_SECONDS,
)
from backend.lambdas.review_worker.handler import (
    AGENT_READ_TIMEOUT_SECONDS as REVIEW_WORKER_WAIT_SECONDS,
)

ROOT = Path(__file__).resolve().parents[3]
# Retrieval, preflight and the Guardrails screen run before the model call.
RETRIEVAL_MARGIN_SECONDS = 20


def _tree() -> ast.Module:
    return ast.parse((ROOT / "backend/agent/runtime_entrypoint.py").read_text(encoding="utf-8"))


def _default(name: str) -> float:
    for node in ast.walk(_tree()):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
        ):
            getenv = node.value.args[0]
            return float(getenv.args[1].value)
    raise AssertionError(f"{name} not found")


def _client_kwargs(name: str) -> dict[str, str]:
    for node in ast.walk(_tree()):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
        ):
            return {kw.arg: ast.unparse(kw.value) for kw in node.value.keywords}
    raise AssertionError(f"{name} not found")


def test_both_reasoning_clients_wait_for_the_whole_answer_with_no_retries():
    review = _client_kwargs("_REASONING_CLIENT")
    deeper = _client_kwargs("_DEEPER_REASONING_CLIENT")
    for kwargs in (review, deeper):
        assert kwargs["no_retries"] == "True"
        assert "stream_deadline_seconds" not in kwargs
    assert review["read_timeout_seconds"] == "_REASONING_READ_TIMEOUT_SECONDS"
    assert deeper["read_timeout_seconds"] == "_DEEPER_REASONING_READ_TIMEOUT_SECONDS"


def test_the_wait_outlasts_botocores_default_and_the_slowest_measured_call():
    # The slowest healthy review measured took 112 s (2026-10-28).
    assert _default("_REASONING_READ_TIMEOUT_SECONDS") > 112
    assert _default("_DEEPER_REASONING_READ_TIMEOUT_SECONDS") > 60


def test_review_call_ends_before_the_review_worker_gives_up():
    worst = _default("_REASONING_READ_TIMEOUT_SECONDS")
    assert worst + RETRIEVAL_MARGIN_SECONDS < REVIEW_WORKER_WAIT_SECONDS


def test_deeper_call_ends_before_the_deeper_worker_gives_up():
    worst = _default("_DEEPER_REASONING_READ_TIMEOUT_SECONDS")
    assert worst + RETRIEVAL_MARGIN_SECONDS < DEEPER_WORKER_WAIT_SECONDS
