"""Prevent accidentally exposing paid integrations before public access opens."""

from pathlib import Path

import hcl2
from hcl2.utils import SerializationOptions

ROOT = Path(__file__).resolve().parents[2]


def _read(name):
    with (ROOT / "infra/modules/api-gateway" / name).open(encoding="utf-8") as source:
        return hcl2.load(
            source, serialization_options=SerializationOptions(strip_string_quotes=True)
        )


def test_every_review_and_upload_route_keeps_its_admin_authorizer():
    checked = set()
    for filename in ("main.tf", "chat.tf"):
        for resource in _read(filename)["resource"]:
            for route in resource.get("aws_apigatewayv2_route", {}).values():
                key = route["route_key"]
                if key == "GET /demo":
                    continue
                checked.add(key)
                assert route["authorization_type"] == "CUSTOM", key
                assert "admin_gate" in route["authorizer_id"], key
    assert {
        "POST /reviews",
        "POST /uploads",
        "POST /reviews/{reviewId}/questions",
    } <= checked


def test_public_chat_default_stays_disabled():
    variables = {
        key: value
        for entry in _read("variables.tf")["variable"]
        for key, value in entry.items()
    }
    assert variables["chat_public_enabled"]["default"] is False


def test_public_activation_is_disabled_and_requires_a_verified_api_id():
    defaults = {
        key: value
        for file in ("admission.tf", "public-edge.tf")
        for entry in _read(file).get("variable", [])
        for key, value in entry.items()
    }
    assert defaults["public_access_enabled"]["default"] is False
    assert defaults["public_edge_enabled"]["default"] is False
    assert defaults["verified_public_api_id"]["default"] == ""
    locals_text = str(_read("admission.tf")["locals"])
    assert (
        "verified_public_api_id == aws_api_gateway_rest_api.public[0].id" in locals_text
    )


def test_rest_stage_has_waf_and_http_submission_uses_admission():
    edge = _read("public-edge.tf")
    resources = {}
    for item in edge["resource"]:
        for kind, values in item.items():
            resources.setdefault(kind, {}).update(values)
    association = resources["aws_wafv2_web_acl_association"]["public"]
    assert "aws_api_gateway_stage.public[0].arn" in association["resource_arn"]
    assert "aws_wafv2_web_acl.public[0].arn" in association["web_acl_arn"]
    for permission in ("public", "preflight"):
        assert (
            "/public/" in resources["aws_lambda_permission"][permission]["source_arn"]
        )
    http = {
        kind: values
        for item in _read("main.tf")["resource"]
        for kind, values in item.items()
        if kind == "aws_apigatewayv2_integration" and "start_review" in values
    }
    integration = http["aws_apigatewayv2_integration"]["start_review"]
    assert "integration_subtype" not in integration
    assert "submit_review" in integration["integration_uri"]


def test_workflow_definition_never_propagates_submission_fields():
    path = ROOT / "infra/modules/step-functions-lambda/main.tf"
    definition = (
        path.read_text(encoding="utf-8")
        .split("definition = jsonencode(", 1)[1]
        .split("\n  tags =", 1)[0]
    )
    for forbidden in (
        "workload_brief",
        "baseline_answers",
        "preflight_fields",
        "valid_findings",
        "parsed_s3_key",
    ):
        assert forbidden not in definition
