from pathlib import Path

from backend.lambdas.get_demo.handler import handler as get_demo
from backend.shared.http import JSON_HEADERS

_LAMBDAS = Path(__file__).resolve().parents[3] / "backend" / "lambdas"


def test_api_responses_carry_the_security_headers():
    headers = get_demo({}, None)["headers"]
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["strict-transport-security"].startswith("max-age=31536000")
    assert headers == JSON_HEADERS


def test_no_handler_builds_its_own_headers():
    # A handler that writes its own header dict would skip the security headers.
    for path in _LAMBDAS.glob("*/handler.py"):
        assert '"content-type": "application/json"' not in path.read_text(encoding="utf-8"), path
