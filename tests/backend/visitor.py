"""A legitimate public visitor, for handler tests.

There is no admin bypass, so every call that reads or writes a review needs
public access on, the review's capability tokens and the visitor's network
identity that wrote it.
"""

from __future__ import annotations

import hashlib
import hmac

READ_TOKEN = "r" * 43
WRITE_TOKEN = "w" * 43
SOURCE_IP = "192.0.2.10"
VISITOR_HASH_KEY = "test-visitor-hash-key-32-characters-long"

HEADERS = {"x-review-read-token": READ_TOKEN, "x-review-write-token": WRITE_TOKEN}
REQUEST_CONTEXT = {"identity": {"sourceIp": SOURCE_IP}}


def enable_public(monkeypatch) -> None:
    monkeypatch.setenv("PUBLIC_ACCESS_ENABLED", "true")
    monkeypatch.setenv("VISITOR_HASH_KEY", VISITOR_HASH_KEY)


def review_fields() -> dict[str, str]:
    """The capability fields a review item needs to belong to this visitor."""
    visitor = hmac.new(VISITOR_HASH_KEY.encode(), SOURCE_IP.encode(), hashlib.sha256).hexdigest()
    return {
        "visitorKey": "v1-" + visitor,
        "readTokenHash": hashlib.sha256(READ_TOKEN.encode()).hexdigest(),
        "writeTokenHash": hashlib.sha256(WRITE_TOKEN.encode()).hexdigest(),
    }
