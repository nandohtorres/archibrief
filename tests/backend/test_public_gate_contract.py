"""Prevent accidentally exposing current paid integrations during Gate 2 work."""

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
