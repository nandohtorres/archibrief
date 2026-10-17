import json

from backend.shared.http import api_handler


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
