from copy import deepcopy

import pytest

from backend.shared.report import build_review_report
from backend.shared.review_scope import finalize_scope, pending_record
from backend.shared.scope_projection import public_review_scope
from tests.backend.p0_scope_fixtures import declaration


def test_projection_counts_and_module_gaps_do_not_expose_internal_bindings():
    pending = pending_record("recorded", [
        declaration(), declaration("random_id", "id"), declaration(key="disabled", instances=0),
    ], [{"address": "module.remote", "reasons": ["remote_source"]}], count_complete=False)
    final = finalize_scope(pending, [["aws_s3_bucket", "main"]], "completed")
    before = deepcopy(final)
    scope = public_review_scope(final)
    assert (scope["known_y"], scope["x"], scope["count_complete"]) == (3, 1, False)
    assert scope["categories"] == {"reviewed": 1, "unsupported": 1, "zero_copy": 1, "other": 0}
    assert scope["module_gaps"] == [{"address": "module.remote", "labels": ["remote module not read"]}]
    assert not {"declarations", "parsed_key", "sent_count", "archive_sha256"} & set(scope)
    assert final == before
    report = build_review_report({"reviewId": "r1"}, {"findings": [], "review_scope": final})
    assert report["review_scope"] == scope


@pytest.mark.parametrize("record", [None, {}, pending_record("unknown_root"), pending_record("recorded")])
def test_missing_invalid_or_pending_coverage_is_unknown_never_zero(record):
    scope = public_review_scope(record)
    assert scope["x"] is scope["known_y"] is scope["categories"] is None


def test_unknown_delivery_keeps_reviewed_count_unknown():
    final = finalize_scope(pending_record("recorded", [declaration()]), [["aws_s3_bucket", "main"]], "unknown")
    assert public_review_scope(final)["x"] is None
    assert public_review_scope(final)["other_reasons"] == [{"label": "AI delivery unconfirmed", "count": 1}]


def test_module_names_with_unsafe_text_are_not_public():
    pending = pending_record("recorded", [], [{"address": "<script>SECRET</script>", "reasons": ["remote_source"]}])
    scope = public_review_scope(finalize_scope(pending, [], "completed"))
    assert scope["module_gaps"][0]["address"] == "module (name unavailable)"
