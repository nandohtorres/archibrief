from backend.agent import graph


def test_deeper_graph_preserves_parent_context_and_output_quality_channels(monkeypatch):
    parent = {"evidence": "original configuration evidence"}
    counts = {"attempted": 2, "accepted": 1, "rejected": 1}
    monkeypatch.setattr(graph, "retrieve_node", lambda state: {"retrieved_chunks": []})

    def reason(state):
        assert state["parent_finding"] == parent
        return {"reasoned_findings": [], "model_output_counts": counts}

    monkeypatch.setattr(graph, "reason_node", reason)
    result = graph.compiled_deeper_graph().invoke({"parent_finding": parent})
    assert result["model_output_counts"] == counts
