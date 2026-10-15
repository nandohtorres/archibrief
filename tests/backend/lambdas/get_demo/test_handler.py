import json

from backend.lambdas.get_demo.handler import handler
from backend.shared.models.finding import Finding


def test_returns_200_with_json_content_type():
    result = handler({}, None)
    assert result["statusCode"] == 200
    assert result["headers"]["content-type"] == "application/json"


def test_response_body_matches_the_reviewreport_contract_shape():
    body = json.loads(handler({}, None)["body"])
    assert body["status"] == "complete"
    assert isinstance(body["baseline_answers"], list) and body["baseline_answers"]
    assert isinstance(body["findings"], list) and body["findings"]
    for item in body["findings"]:
        assert set(item.keys()) == {"record", "presentation"}
        assert set(item["presentation"].keys()) == {"priority", "short_label"}


def test_every_finding_record_is_a_schema_valid_finding():
    body = json.loads(handler({}, None)["body"])
    for item in body["findings"]:
        Finding.model_validate(item["record"])  # raises if invalid


def test_is_fully_static_no_findings_reference_a_live_pipeline_run():
    # Every citation's exact_text_span is explicitly labeled illustrative
    # (see handler.py's module docstring) — pins down that this stays
    # honest about not being a real corpus-grounded run, rather than
    # silently drifting to look like one on a future edit.
    body = json.loads(handler({}, None)["body"])
    for item in body["findings"]:
        citation = item["record"]["citation"]
        if citation is not None:
            assert "Illustrative" in citation["exact_text_span"]
