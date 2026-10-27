from backend.agent.nodes.preflight import (
    FieldOutcome,
    evaluate_all_fields,
    preflight_node,
)


def test_answered_field_returns_answered():
    result = evaluate_all_fields({"regulatory_data_residency": "EU-only"})
    assert result["regulatory_data_residency"].outcome == FieldOutcome.ANSWERED
    assert result["regulatory_data_residency"].value == "EU-only"


def test_no_field_pauses_a_review():
    result = evaluate_all_fields({})
    assert result["regulatory_data_residency"].outcome == FieldOutcome.UNKNOWN
    assert all(field.outcome != FieldOutcome.PAUSED for field in result.values())


def test_unanswered_conservative_field_gets_assumption():
    result = evaluate_all_fields({})
    field = result["expected_traffic_scale"]
    assert field.outcome == FieldOutcome.ASSUMPTION
    assert field.is_assumption is True
    assert field.value is not None


def test_preflight_node_runs_on_without_the_regulatory_answer():
    # submit_review requires it; a review that somehow lacks it still runs.
    result = preflight_node({"baseline_answers": {}})
    assert result["status"] == "ready"
    assert result["needs_clarification"] == []
    assert (
        result["preflight_fields"]["regulatory_data_residency"]["outcome"] == "unknown"
    )


def test_preflight_node_ready_when_required_field_answered():
    state = {"baseline_answers": {"regulatory_data_residency": "US-only"}}
    result = preflight_node(state)
    assert result["status"] == "ready"
    assert result["needs_clarification"] == []
