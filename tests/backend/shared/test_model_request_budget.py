from copy import deepcopy

from backend.shared.model_request_budget import request_utf8_bytes


def test_counts_unicode_bytes_and_all_request_sections_without_mutation():
    request = {"system": [{"text": "é"}], "messages": [], "toolConfig": {}, "modelId": "m"}
    before = deepcopy(request)
    size = request_utf8_bytes(request)
    assert request == before
    assert request_utf8_bytes(dict(reversed(list(request.items())))) == size
    request["system"][0]["text"] = "e"
    assert request_utf8_bytes(request) == size - 1
    request["toolConfig"] = {"tools": [{"inputSchema": {"json": {"description": "x" * 1000}}}]}
    assert request_utf8_bytes(request) > size + 1000
