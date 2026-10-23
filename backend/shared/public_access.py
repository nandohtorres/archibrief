"""Server-validated challenges, network identifiers and review capabilities."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import urllib.request

import boto3
from botocore.config import Config

from backend.shared.admission import AdmissionDenied
from backend.shared.retention import review_is_live


def headers(event: dict) -> dict:
    return {str(key).lower(): value for key, value in (event.get("headers") or {}).items()}


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def public_enabled() -> bool:
    # Every handler checks this itself; the API has no authorizer.
    return os.environ.get("PUBLIC_ACCESS_ENABLED", "false").lower() == "true"


def visitor_key(event: dict) -> str:
    secret = os.environ.get("VISITOR_HASH_KEY", "")
    if len(secret) < 32:
        raise AdmissionDenied("admission_unavailable")
    context = event.get("requestContext") or {}
    # Trust the API service's peer metadata, never a viewer-supplied header.
    raw = (context.get("identity") or {}).get("sourceIp") or (context.get("http") or {}).get(
        "sourceIp"
    )
    try:
        address = ipaddress.ip_address(raw)
    except (ValueError, TypeError):
        raise AdmissionDenied("admission_unavailable") from None
    network = (
        str(ipaddress.ip_network(f"{address}/64", strict=False))
        if address.version == 6
        else str(address)
    )
    return "v1-" + hmac.new(secret.encode(), network.encode(), hashlib.sha256).hexdigest()


def capability_allowed(event: dict, review: dict, *, write: bool = False) -> bool:
    if not review_is_live(review):
        return False
    if not public_enabled():
        return False
    provided = headers(event).get("x-review-write-token" if write else "x-review-read-token", "")
    expected = review.get("writeTokenHash" if write else "readTokenHash", "")
    if not isinstance(provided, str) or not 32 <= len(provided) <= 128 or not expected:
        return False
    if not hmac.compare_digest(token_hash(provided), str(expected)):
        return False
    try:
        return not write or hmac.compare_digest(
            visitor_key(event), str(review.get("visitorKey", ""))
        )
    except AdmissionDenied:
        return False


def verify_upload_challenge(event: dict, token: str) -> str:
    if not public_enabled():
        raise AdmissionDenied("public_access_closed")
    if not isinstance(token, str) or not 1 <= len(token) <= 2048:
        raise AdmissionDenied("challenge_required")
    parameter = os.environ.get("TURNSTILE_SECRET_PARAMETER_NAME", "")
    # Every hostname that serves the site (apex and www), comma-separated.
    hostnames = {
        name.strip()
        for name in os.environ.get("TURNSTILE_HOSTNAMES", "").split(",")
        if name.strip()
    }
    if not parameter or not hostnames:
        raise AdmissionDenied("admission_unavailable")
    try:
        secret = boto3.client(
            "ssm",
            config=Config(connect_timeout=1, read_timeout=2, retries={"total_max_attempts": 1}),
        ).get_parameter(Name=parameter, WithDecryption=True)["Parameter"]["Value"]
        request = urllib.request.Request(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data=json.dumps({"secret": secret, "response": token}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            verdict = json.loads(response.read(8192))
    except Exception:  # noqa: BLE001 - all challenge failures must fail closed
        raise AdmissionDenied("challenge_unavailable") from None
    if (
        not isinstance(verdict, dict)
        or verdict.get("success") is not True
        or verdict.get("hostname") not in hostnames
        or verdict.get("action") != "archibrief-upload"
    ):
        raise AdmissionDenied("challenge_rejected")
    return visitor_key(event)
