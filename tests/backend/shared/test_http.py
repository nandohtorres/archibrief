import json
from pathlib import Path

from backend.lambdas.get_demo.handler import handler as get_demo
from backend.shared.http import JSON_HEADERS, api_handler

_LAMBDAS = Path(__file__).resolve().parents[3] / "backend" / "lambdas"


def test_api_responses_carry_the_security_headers():
    headers = get_demo({}, None)["headers"]
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["strict-transport-security"].startswith("max-age=31536000")
    assert headers == JSON_HEADERS


def test_no_handler_builds_its_own_headers():
    # A handler that writes its own header dict would skip the security headers.
    for path in _LAMBDAS.glob("*/handler.py"):
        assert '"content-type": "application/json"' not in path.read_text(
            encoding="utf-8"
        ), path


def test_preflight_and_untrusted_origins_never_reach_application_code(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", json.dumps(["https://example.test"]))
    calls = []

    @api_handler
    def endpoint(event, context):
        calls.append(event)
        return {"statusCode": 200, "body": "private"}

    allowed = {"httpMethod": "OPTIONS", "headers": {"Origin": "https://example.test"}}
    assert endpoint(allowed, None)["statusCode"] == 204
    assert calls == []
    assert (
        endpoint(
            {"httpMethod": "POST", "headers": {"Origin": "https://evil.test"}}, None
        )["statusCode"]
        == 403
    )
    assert calls == []
    result = endpoint({**allowed, "httpMethod": "GET"}, None)
    assert result["headers"]["access-control-allow-origin"] == "https://example.test"
    assert result["headers"]["cache-control"] == "no-store"


def test_wrapped_responses_carry_the_security_headers():
    @api_handler
    def endpoint(event, context):
        return {
            "statusCode": 200,
            "headers": {"content-type": "application/json"},
            "body": "{}",
        }

    headers = endpoint({"httpMethod": "GET"}, None)["headers"]
    for name, value in JSON_HEADERS.items():
        assert headers[name] == value
