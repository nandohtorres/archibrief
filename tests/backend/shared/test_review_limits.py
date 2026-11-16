from copy import deepcopy

import pytest

from backend.shared.review_limits import scope_rejection_code
from backend.shared.review_scope import finalize_scope, pending_record
from tests.backend.p0_scope_fixtures import declaration


@pytest.mark.parametrize("count", [0, 1, 49, 50, 51, 75, 100])
@pytest.mark.parametrize("final", [False, True])
def test_boundary_counts_declarations_before_creation_and_provider_filtering(count, final):
    entries = [
        declaration("random_id" if n % 2 else "aws_s3_bucket", f"r{n}", instances=0)
        for n in range(count)
    ]
    scope = pending_record("recorded", entries)
    if final:
        scope = finalize_scope(scope, [], "not_invoked")
    before = deepcopy(scope)
    assert scope_rejection_code(scope) == ("resource_limit_exceeded" if count > 50 else None)
    assert scope == before


def test_unreadable_modules_and_unknown_instances_allow_labeled_partial_review():
    scope = pending_record(
        "recorded", [declaration(instances=None)],
        [{"address": "module.remote", "reasons": ["remote_source"]}],
        count_complete=False, gaps_complete=False, warnings=["skipped_tf_json"],
    )
    assert scope_rejection_code(scope) is None


@pytest.mark.parametrize("scope", [None, {}, {"known_y": 1}, pending_record("unknown_root"), pending_record("malformed")])
def test_unknown_or_malformed_scope_cannot_authorize_a_review(scope):
    assert scope_rejection_code(scope) == "scope_manifest_required"


def test_forged_small_count_and_duplicate_identity_are_not_eligibility_proof():
    scope = pending_record("recorded", [declaration(key=f"r{n}") for n in range(51)])
    scope["known_y"] = 1
    assert scope_rejection_code(scope) == "scope_manifest_required"
    scope = pending_record("recorded", [declaration(), declaration()])
    assert scope_rejection_code(scope) == "scope_manifest_required"
