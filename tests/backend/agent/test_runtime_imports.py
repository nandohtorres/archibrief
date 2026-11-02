"""The AgentCore runtime must import without the ingestion-only libraries.

backend/agent/build_runtime_package.py leaves the HCL parser, PDF and HTML
libraries out of the runtime package. Locally every library is installed,
so a runtime module that starts importing one passes every other test and
then fails in AWS: on 2026-11-02 reason.py reached the HCL parser through
terraform_observations.py, and every review's model step failed at import.
This imports the runtime in a fresh interpreter with those libraries
blocked.
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
# Never in the runtime package (build_runtime_package.py, runtime_requirements.in).
INGESTION_ONLY = ("hcl2", "lark", "bs4", "pypdf")

_PROBE = textwrap.dedent(
    """
    import importlib.abc
    import sys
    import types

    BLOCKED = set(sys.argv[1].split(","))


    class Block(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in BLOCKED:
                raise ModuleNotFoundError(f"No module named {name!r} (not in the runtime package)")
            return None


    sys.meta_path.insert(0, Block())

    # The AgentCore SDK only ships in the runtime package; a stand-in is enough
    # to import the entrypoint.
    class App:
        def entrypoint(self, function):
            return function

        def run(self):
            pass

    runtime = types.ModuleType("bedrock_agentcore.runtime")
    runtime.BedrockAgentCoreApp = App
    sys.modules["bedrock_agentcore"] = types.ModuleType("bedrock_agentcore")
    sys.modules["bedrock_agentcore.runtime"] = runtime

    import backend.agent.runtime_entrypoint  # noqa: F401
    """
)


def test_the_runtime_imports_without_ingestion_only_libraries():
    env = {
        **os.environ,
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_REGION": "us-east-1",
        "PYTHONPATH": str(ROOT),
    }
    result = subprocess.run(
        [sys.executable, "-c", _PROBE, ",".join(INGESTION_ONLY)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-2000:]
