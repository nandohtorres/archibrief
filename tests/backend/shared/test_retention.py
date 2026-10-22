from datetime import UTC, datetime

import pytest

from backend.shared.retention import (
    REVIEW_LIFETIME_SECONDS,
    review_expires_at,
    review_is_live,
)

NOW = 1_800_000_000


@pytest.mark.parametrize(
    "item",
    [
        {},
        {"ttl": None},
        {"ttl": "bad"},
        {"ttl": NOW},
        {"createdAt": "bad"},
        {"createdAt": "2026-01-01"},
    ],
)
def test_unknown_malformed_or_elapsed_lifetimes_fail_closed(item):
    assert not review_is_live(item, NOW)


def test_workflow_creation_timestamp_is_a_legacy_expiry_source():
    item = {"createdAt": datetime.fromtimestamp(NOW, UTC).isoformat()}
    assert review_expires_at(item) == NOW + REVIEW_LIFETIME_SECONDS
    assert review_is_live(item, NOW + REVIEW_LIFETIME_SECONDS - 1)
    assert not review_is_live(item, NOW + REVIEW_LIFETIME_SECONDS)


def test_explicit_ttl_cannot_extend_the_original_lifetime():
    item = {
        "createdAt": datetime.fromtimestamp(NOW, UTC).isoformat(),
        "ttl": NOW + 10 * REVIEW_LIFETIME_SECONDS,
    }
    assert review_expires_at(item) == NOW + REVIEW_LIFETIME_SECONDS
    item["ttl"] = NOW + 10
    assert review_expires_at(item) == NOW + 10
