from backend.agent.nodes.preflight import (
    FieldOutcome,
    evaluate_all_fields,
    preflight_node,
)


def test_answered_field_returns_answered():
    result = evaluate_all_fields({"regulatory_data_residency": "EU-only"})
    assert result["regulatory_data_residency"].outcome == FieldOutcome.ANSWERED
    assert result["regulatory_data_residency"].value == "EU-only"


def test_unanswered_required_field_pauses():
    result = evaluate_all_fields({})
    assert result["regulatory_data_residency"].outcome == FieldOutcome.PAUSED


def test_unanswered_conservative_field_gets_assumption():
    result = evaluate_all_fields({})
    field = result["expected_traffic_scale"]
    assert field.outcome == FieldOutcome.ASSUMPTION
    assert field.is_assumption is True
    assert field.value is not None


def test_preflight_node_flags_needs_clarification():
    state = {"baseline_answers": {}}
    result = preflight_node(state)
    assert result["status"] == "needs_clarification"
    assert "regulatory_data_residency" in result["needs_clarification"]


def test_preflight_node_ready_when_required_field_answered():
    state = {"baseline_answers": {"regulatory_data_residency": "US-only"}}
    result = preflight_node(state)
    assert result["status"] == "ready"
    assert result["needs_clarification"] == []
