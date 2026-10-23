import json
import time
from unittest.mock import MagicMock

import pytest

from backend.shared import public_access as access
from backend.shared.admission import AdmissionDenied


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("PUBLIC_ACCESS_ENABLED", "true")
    monkeypatch.setenv("VISITOR_HASH_KEY", "v" * 32)
    monkeypatch.setenv("TURNSTILE_SECRET_PARAMETER_NAME", "/test/turnstile")
    monkeypatch.setenv("TURNSTILE_HOSTNAMES", "example.test, www.example.test")
    monkeypatch.setenv("ADMIN_KEY", "admin-secret")
    monkeypatch.setattr(
        access.boto3,
        "client",
        lambda *a, **k: MagicMock(
            get_parameter=lambda **kw: {"Parameter": {"Value": "provider-secret"}}
        ),
    )


def _event(ip="192.0.2.10", **headers):
    return {"headers": headers, "requestContext": {"identity": {"sourceIp": ip}}}


def test_read_and_write_capabilities_are_distinct_and_write_is_owner_bound(configured):
    read, write = "r" * 43, "w" * 43
    review = {
        "ttl": int(time.time()) + 3600,
        "readTokenHash": access.token_hash(read),
        "writeTokenHash": access.token_hash(write),
        "visitorKey": access.visitor_key(_event()),
    }
    assert access.capability_allowed(_event(**{"x-review-read-token": read}), review)
    assert not access.capability_allowed(
        _event(**{"x-review-write-token": read}), review, write=True
    )
    assert access.capability_allowed(
        _event(**{"x-review-write-token": write}), review, write=True
    )
    assert not access.capability_allowed(
        _event("192.0.2.11", **{"x-review-write-token": write}), review, write=True
    )
    review["ttl"] = 1
    assert not access.capability_allowed(
        _event(**{"x-review-read-token": read}), review
    )


def test_forwarded_headers_cannot_change_visitor_and_ipv6_uses_a_64_prefix(configured):
    assert access.visitor_key(_event()) == access.visitor_key(
        _event(**{"x-forwarded-for": "198.51.100.1"})
    )
    assert access.visitor_key(_event("2001:db8::1")) == access.visitor_key(
        _event("2001:db8::2")
    )
    assert access.visitor_key(_event("2001:db8::1")) != access.visitor_key(
        _event("2001:db8:1::1")
    )


@pytest.mark.parametrize(
    "verdict",
    [
        {"success": False},
        {"success": True, "hostname": "evil.test", "action": "archibrief-upload"},
        {"success": True, "hostname": "example.test", "action": "other"},
        [],
    ],
)
def test_challenge_result_must_match_hostname_action_and_success(
    configured, monkeypatch, verdict
):
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(verdict).encode()
    monkeypatch.setattr(access.urllib.request, "urlopen", lambda *a, **k: response)
    with pytest.raises(AdmissionDenied, match="challenge_rejected"):
        access.verify_upload_challenge(_event(), "challenge-token")


def test_challenge_outage_and_missing_configuration_fail_closed(
    configured, monkeypatch
):
    monkeypatch.setattr(
        access.urllib.request,
        "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(TimeoutError()),
    )
    with pytest.raises(AdmissionDenied, match="challenge_unavailable"):
        access.verify_upload_challenge(_event(), "token")
    monkeypatch.delenv("TURNSTILE_SECRET_PARAMETER_NAME")
    with pytest.raises(AdmissionDenied, match="admission_unavailable"):
        access.verify_upload_challenge(_event(), "token")


@pytest.mark.parametrize("hostname", ["example.test", "www.example.test"])
def test_challenge_accepts_every_configured_hostname(configured, monkeypatch, hostname):
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(
        {"success": True, "hostname": hostname, "action": "archibrief-upload"}
    ).encode()
    monkeypatch.setattr(access.urllib.request, "urlopen", lambda *a, **k: response)
    assert access.verify_upload_challenge(_event(), "token") == access.visitor_key(_event())


def test_public_access_is_closed_by_default_even_with_a_token(configured, monkeypatch):
    monkeypatch.delenv("PUBLIC_ACCESS_ENABLED")
    with pytest.raises(AdmissionDenied, match="public_access_closed"):
        access.verify_upload_challenge(_event(), "token")


def test_successful_challenge_is_verified_on_the_server(configured, monkeypatch):
    calls = []

    def verify(request, timeout):
        calls.append((request, timeout))
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {"success": True, "hostname": "example.test", "action": "archibrief-upload"}
        ).encode()
        return response

    monkeypatch.setattr(access.urllib.request, "urlopen", verify)
    assert access.verify_upload_challenge(_event(), "token") == access.visitor_key(
        _event()
    )
    request, timeout = calls[0]
    assert (
        request.full_url == "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    )
    assert json.loads(request.data) == {
        "secret": "provider-secret",
        "response": "token",
    }
    assert timeout == 3
