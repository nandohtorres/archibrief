"""The runtime's model call must time out before the workers stop waiting
for the runtime, and never fall back to botocore's 60 s default.

The runtime module imports the AgentCore SDK, which only ships in the
runtime package, so these checks read the source instead of importing it.
"""

import ast
import re
from pathlib import Path

from backend.lambdas.deeper_review.worker import AGENT_READ_TIMEOUT_SECONDS

ROOT = Path(__file__).resolve().parents[3]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _reasoning_timeout_default() -> float:
    tree = ast.parse(_source("backend/agent/runtime_entrypoint.py"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "_REASONING_READ_TIMEOUT_SECONDS"
        ):
            getenv = node.value.args[0]
            return float(getenv.args[1].value)
    raise AssertionError("_REASONING_READ_TIMEOUT_SECONDS not found")


def _reasoning_client_kwargs() -> set[str]:
    tree = ast.parse(_source("backend/agent/runtime_entrypoint.py"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "_REASONING_CLIENT"
        ):
            return {kw.arg for kw in node.value.keywords}
    raise AssertionError("_REASONING_CLIENT not found")


def _worker_wait_seconds(path: str) -> int:
    waits = re.findall(r"read_timeout_seconds=(\d+)", _source(path))
    assert waits, f"no AgentCore read timeout in {path}"
    return min(int(w) for w in waits)


def test_reasoning_call_sets_its_own_timeout_without_retries():
    assert {"read_timeout_seconds", "no_retries"} <= _reasoning_client_kwargs()


def test_reasoning_timeout_outlasts_a_long_review_but_ends_before_the_workers_give_up():
    timeout = _reasoning_timeout_default()
    assert timeout > 60
    assert timeout < _worker_wait_seconds("backend/lambdas/review_worker/handler.py")
    assert timeout < AGENT_READ_TIMEOUT_SECONDS
