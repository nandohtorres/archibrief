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


def test_there_is_no_admin_path_or_unprotected_api():
    module = ROOT / "infra/modules/api-gateway"
    text = "\n".join(path.read_text(encoding="utf-8") for path in module.glob("*.tf"))
    # Every route is on the WAF-protected REST stage; the old HTTP API and
    # the admin key that bypassed the public limits are gone.
    for gone in ("aws_apigatewayv2_api\"", "aws_apigatewayv2_route", "ADMIN_KEY", "admin_key"):
        assert gone not in text, gone
    routes = str(_read("public-edge.tf")["locals"])
    for function in ("create_upload", "submit_review", "ask_question", "get_review"):
        assert function in routes, function


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


def test_rest_stage_has_waf_and_submission_uses_admission():
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
    # POST /reviews reaches submit_review, which admits the review, never
    # Step Functions directly.
    routes = _read("public-edge.tf")["locals"][0]["public_routes"]
    assert "submit_review" in str(routes).split("submit", 1)[1].split("read", 1)[0]


def test_rest_front_door_relies_on_handler_gates_and_returns_cors_errors():
    resources = {}
    for item in _read("public-edge.tf")["resource"]:
        for kind, values in item.items():
            resources.setdefault(kind, {}).update(values)
    # A header-based authorizer rejects visitors who send no header before
    # the handler's own PUBLIC_ACCESS_ENABLED check runs.
    assert "aws_api_gateway_authorizer" not in resources
    assert resources["aws_api_gateway_method"]["public"]["authorization"] == "NONE"
    response = resources["aws_api_gateway_gateway_response"]["public"]
    assert "Access-Control-Allow-Origin" in str(response["response_parameters"])


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
