import time
from types import SimpleNamespace

import pytest

from backend.agent.request_budget import generation_request, prepare_envelope
from backend.shared.clients import BedrockReasoningClient
from backend.shared.admission import AdmissionDenied
from backend.shared.model_request_budget import (
    MAX_REQUEST_BYTES, GenerationBudget, RequestBudgetExceeded, request_utf8_bytes,
)
from backend.shared.scope_admission import (
    claim_input_screen, checked_request_envelope,
)
from backend.shared.review_screen import screen_review
from tests.backend.shared.test_scope_admission import operation  # noqa: F401


class Service:
    def __init__(self, count=1000):
        self.count = count
        self.calls = []

    def count_tokens(self, **kwargs):
        self.calls.append(("count", kwargs))
        if isinstance(self.count, Exception):
            raise self.count
        return {"inputTokens": self.count}

    def converse(self, **kwargs):
        self.calls.append(("generate", kwargs))
        return {"stopReason": "tool_use", "output": {"message": {"content": [
            {"toolUse": {"name": "emit_findings", "input": {"findings": []}}},
        ]}}}


def client(service, *, deadline=None):
    result = object.__new__(BedrockReasoningClient)
    result.model_id = "us.anthropic.claude-sonnet-4-6"
    result._client = service
    result.token_counter = None
    result.generation_budget = GenerationBudget("initial", 400000, deadline or time.monotonic() + 100)
    return result


def call(value, *, schema=None):
    return value.converse_structured(
        system_prompt="private system", user_content="private user", max_tokens=12288,
        tool_name="emit_findings", tool_description="findings", input_schema=schema or {"type": "object"},
    )


def test_generation_boundary_counts_complete_schema_then_dispatches_once():
    service = Service()
    value = client(service)
    assert call(value) == {"findings": []}
    assert [name for name, _ in service.calls] == ["count", "generate"]
    counted = service.calls[0][1]["input"]["converse"]
    generated = service.calls[1][1]
    assert counted == {key: generated[key] for key in ("system", "messages", "toolConfig")}
    with pytest.raises(RequestBudgetExceeded, match="dispatch_limit"):
        call(value)
    assert len(service.calls) == 2


@pytest.mark.parametrize("count,code", [(100000, "cost_limit"), (True, "token_count"), (-1, "token_count"), (TimeoutError("private"), "token_count")])
def test_unaffordable_unknown_or_bad_counts_never_generate(count, code):
    service = Service(count)
    with pytest.raises(RequestBudgetExceeded, match=code):
        call(client(service))
    assert [name for name, _ in service.calls] == ["count"]


def test_schema_overhead_and_deadline_stop_before_even_unbilled_counting():
    service = Service()
    with pytest.raises(RequestBudgetExceeded, match="input_limit"):
        call(client(service), schema={"description": "x" * MAX_REQUEST_BYTES})
    with pytest.raises(RequestBudgetExceeded, match="dispatch_limit"):
        call(client(service, deadline=time.monotonic() - 1))
    assert service.calls == []


def test_large_fifty_declaration_input_is_rejected_without_count_or_paid_screen():
    payload = {
        "review_id": "test", "workload_brief": "test", "baseline_answers": {},
        "terraform_resources": {"resources": [
            {"type": "aws_iam_role", "name": f"r{n}", "settings": {"policy": "X" * 3000}}
            for n in range(50)
        ]},
    }
    service = Service()
    with pytest.raises(RequestBudgetExceeded, match="input_limit"):
        prepare_envelope(payload, service, 400000)
    assert service.calls == []


def test_pre_retrieval_envelope_includes_all_fixed_overhead_and_evidence_allowance():
    payload = {"workload_brief": "small", "baseline_answers": {}, "terraform_resources": {"resources": []}}
    service = Service()
    envelope = prepare_envelope(payload, service, 400000)
    assert envelope["request_bound_bytes"] > request_utf8_bytes(generation_request(payload, []))
    assert envelope["cost_bound_micro_usd"] <= 400000
    assert [name for name, _ in service.calls] == ["count"]


def test_replayed_screen_cannot_bill_again(operation):  # noqa: F811
    calls = []
    with pytest.raises(AdmissionDenied, match="already_attempted"):
        screen_review(operation.bound, SimpleNamespace(check=lambda *args, **kwargs: calls.append(args)))
    assert calls == []


def test_missing_or_forged_budget_stops_before_guardrails(operation):  # noqa: F811
    key = {"counterKey": "operation#review-1#initial"}
    operation.table.update_item(Key=key, UpdateExpression="REMOVE request_budget, screen_status")
    with pytest.raises(AdmissionDenied, match="budget_unavailable"):
        claim_input_screen(operation.bound)
    with pytest.raises(AdmissionDenied, match="budget_unavailable"):
        checked_request_envelope(operation.bound)


def test_deadline_crossed_during_embedding_stops_vector_dispatch():
    from backend.agent.nodes.retrieve import vector_search

    now = [0]
    calls = []

    def embed(text):
        calls.append("embed")
        now[0] = 11
        return [1.0]

    adapter = SimpleNamespace(embed=embed, query_vectors=lambda **kwargs: calls.append("vectors"))
    budget = GenerationBudget("initial", 400000, 10, clock=lambda: now[0])
    with pytest.raises(RequestBudgetExceeded, match="dispatch_limit"):
        vector_search("query", adapter, adapter, budget=budget)
    assert calls == ["embed"]


def test_retrieval_excludes_whole_oversized_unicode_chunks_and_counts_omissions():
    from backend.agent.nodes.retrieve import retrieve_node
    from backend.shared.model_request_budget import evidence_bytes, MAX_EVIDENCE_BYTES

    text = "quoted \\\" AWS guidance é"
    chunks = [
        {"key": "large", "metadata": {"chunk_id": "large", "text": "é" * 44000}},
        {"key": "small", "metadata": {"chunk_id": "small", "text": text}},
    ]
    adapter = SimpleNamespace(embed=lambda text: [1.0], query_vectors=lambda **kwargs: chunks)
    result = retrieve_node({
        "retrieval_query": "query", "embedding_client": adapter, "vectors_client": adapter,
        "generation_budget": GenerationBudget("initial", 400000, time.monotonic() + 100),
    })
    assert result["retrieval_omitted_count"] == 1
    assert [c["chunk_id"] for c in result["retrieved_chunks"]] == ["small"]
    assert result["retrieved_chunks"][0]["text"] == text
    assert evidence_bytes(result["retrieved_chunks"]) <= MAX_EVIDENCE_BYTES


def test_budget_lookup_rechecks_receipt_released_between_reads(operation, monkeypatch):  # noqa: F811
    from backend.shared import scope_admission as admission

    original = admission._read_operation
    calls = []

    def read(key):
        row = original(key)
        calls.append(key)
        if len(calls) == 2:
            row["released"] = True
        return row

    monkeypatch.setattr(admission, "_read_operation", read)
    with pytest.raises(AdmissionDenied, match="budget_unavailable"):
        checked_request_envelope(operation.bound)


def test_real_reasoning_adapter_must_share_the_authorized_budget(operation):  # noqa: F811
    from backend.shared.scope_admission import authorize_payload, check_paid_scope

    value = client(Service())
    state = {
        "review_id": "review-1", "paid_scope_context": authorize_payload(operation.bound),
        "generation_budget": value.generation_budget,
    }
    check_paid_scope(state, value)
    wrapped = SimpleNamespace(_wrapped=value)
    check_paid_scope(state, wrapped)
    value.generation_budget = None
    for adapter in (value, wrapped):
        with pytest.raises(AdmissionDenied, match="budget_unavailable"):
            check_paid_scope(state, adapter)
