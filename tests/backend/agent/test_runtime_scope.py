"""Execute the real entrypoint against fake graphs and moto-backed admission.

No service/model calls. Compiled LangGraph integration remains a separate check.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from backend.agent.nodes.reason import reason_node
from backend.agent.nodes.retrieve import retrieve_node
from backend.shared.admission import AdmissionDenied
from backend.shared.clients import (
    BedrockEmbeddingClient,
    BedrockReasoningClient,
    GuardrailsClient,
)
from tests.backend.shared.test_scope_admission import operation  # noqa: F401


@pytest.fixture
def runtime(operation, monkeypatch):  # noqa: F811
    states = []
    graph = SimpleNamespace(invoke=lambda state: states.append(state) or {})
    fake_graph = ModuleType("backend.agent.graph")
    fake_graph.ReviewState = dict
    fake_graph.compiled_graph = lambda: graph
    fake_graph.compiled_deeper_graph = lambda: graph
    monkeypatch.setitem(sys.modules, "backend.agent.graph", fake_graph)
    sdk = ModuleType("bedrock_agentcore.runtime")
    sdk.BedrockAgentCoreApp = type("App", (), {"entrypoint": lambda self, fn: fn})
    monkeypatch.setitem(sys.modules, "bedrock_agentcore", ModuleType("bedrock_agentcore"))
    monkeypatch.setitem(sys.modules, "bedrock_agentcore.runtime", sdk)
    path = Path(__file__).resolve().parents[3] / "backend/agent/runtime_entrypoint.py"
    spec = importlib.util.spec_from_file_location("scope_runtime_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, states


def test_direct_runtime_without_authority_stops_before_graph(runtime):
    module, states = runtime
    for mode in ("initial", "deeper", "unknown"):
        result = module.invoke({"review_id": "review-1", "mode": mode, "known_y": 1}, None)
        assert result["status"] == "admission_denied"
    assert states == []


def test_runtime_payload_tampering_cannot_reach_graph(runtime, operation):  # noqa: F811
    module, states = runtime
    assert module.invoke({**operation.bound, "workload_brief": "changed"}, None)["status"] == "admission_denied"
    assert states == []


def test_runtime_uses_authorized_payload_and_server_owned_token_limit(runtime, operation):  # noqa: F811
    from backend.shared.scope_admission import prepare_operation

    module, states = runtime
    # A fresh, internally prepared operation, never an unsigned client override.
    operation.table.update_item(Key={"counterKey": "operation#review-1#initial"}, UpdateExpression="REMOVE runtime_payload_sha256, screen_status, request_budget, analysis_deadline")
    payload = prepare_operation(operation.review, operation.scope, {
        "review_id": "review-1", "workload_brief": "test", "retrieval_query": "test", "max_tokens": 999999,
    }, operation="initial", job_id="review-1")
    from backend.agent.request_budget import prepare_envelope
    from backend.shared.scope_admission import record_request_envelope, claim_input_screen, finish_input_screen
    record_request_envelope(payload, prepare_envelope(payload, SimpleNamespace(count_tokens=lambda **kw: {"inputTokens": 1000}), 400000))
    finish_input_screen(claim_input_screen(payload), True)
    assert module.invoke(payload, None)["status"] == "complete"
    assert len(states) == 1
    assert states[0]["max_tokens"] == module._MAX_TOKENS
    assert states[0]["paid_scope_context"].review_id == "review-1"


def test_direct_real_nodes_stop_before_paid_clients():
    embedding = object.__new__(BedrockEmbeddingClient)
    reasoning = object.__new__(BedrockReasoningClient)
    guard = object.__new__(GuardrailsClient)
    with pytest.raises(AdmissionDenied):
        retrieve_node({"review_id": "review-1", "retrieval_query": "test", "embedding_client": embedding, "vectors_client": object()})
    with pytest.raises(AdmissionDenied):
        reason_node({"review_id": "review-1", "guardrails_client": guard, "reasoning_client": reasoning})
