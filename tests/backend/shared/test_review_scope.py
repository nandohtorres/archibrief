"""P0 contract sections 2–5: outcomes, classification and record validation."""

import json
from copy import deepcopy

import pytest

from tests.backend.p0_scope_fixtures import (
    completed_scope,
    declaration,
    pending_scope,
    scope_api,
)


def test_pending_row_has_unknown_membership_sent_and_counts():
    record = pending_scope([declaration(), declaration("random_id", "id")])
    assert scope_api().validate_scope(record) == []
    assert record["x"] is record["sent_count"] is record["model_outcome"] is None
    for item in record["declarations"]:
        assert all(
            item[key] is None for key in ("in_summary", "sent", "category", "reason")
        )


@pytest.mark.parametrize(
    "outcome,x,sent_count,member_sent,counts",
    [
        ("completed", 1, 2, True, (1, 2, 2, 1)),
        ("not_invoked", 0, 0, False, (0, 2, 2, 2)),
        ("unknown", None, None, None, (0, 2, 2, 2)),
    ],
)
def test_sent_and_x_outcome_table_and_category_invariant(
    outcome, x, sent_count, member_sent, counts
):
    pending = pending_scope(
        [
            declaration(key="included"),
            declaration(key="capped"),
            declaration("random_id", "included"),
            declaration("random_id", "capped"),
            declaration(key="zero", instances=0),
            declaration("random_id", "zero", instances=0),
        ]
    )
    members = [["aws_s3_bucket", "included"], ["random_id", "included"]]
    result = scope_api().finalize_scope(pending, members, outcome)
    assert result["status"] == "final"
    assert result["model_outcome"] == outcome
    assert result["x"] == x
    assert result["sent_count"] == sent_count
    assert result["known_y"] == 6
    assert result["categories"] == dict(
        zip(("reviewed", "zero_copy", "unsupported", "other"), counts)
    )
    assert sum(result["categories"].values()) == result["known_y"]
    for index, item in enumerate(result["declarations"]):
        included = index in (0, 2)
        assert item["in_summary"] is included
        assert item["sent"] is (member_sent if included else False)
    assert [d["category"] for d in result["declarations"]][2:] == [
        "unsupported",
        "unsupported",
        "zero_copy",
        "zero_copy",
    ]
    assert scope_api().validate_scope(result) == []


@pytest.mark.parametrize("outcome", ["completed", "not_invoked", "unknown"])
@pytest.mark.parametrize(
    "kind,retained,reason",
    [
        ("aws_Custom", False, "not_retained"),
        ("aws_s3_bucket", False, "not_retained"),
        ("aws_Custom", True, "summary_filtered"),
        ("aws_s3_bucket", True, "summary_cap"),
    ],
)
def test_other_reason_first_match_wins_before_model_outcome(
    outcome, kind, retained, reason
):
    # ASSUMPTION: see Q3; even lost bodies can carry a known string key.
    result = scope_api().finalize_scope(
        pending_scope([declaration(kind, retained=retained)]),
        [],
        outcome,
    )
    item = result["declarations"][0]
    assert (item["category"], item["reason"], item["sent"]) == ("other", reason, False)


@pytest.mark.parametrize(
    "outcome,reason",
    [
        ("not_invoked", "model_not_invoked"),
        ("unknown", "outcome_unknown"),
    ],
)
def test_summary_member_gets_outcome_reason(outcome, reason):
    result = scope_api().finalize_scope(
        pending_scope([declaration()]),
        [["aws_s3_bucket", "main"]],
        outcome,
    )
    assert result["declarations"][0]["category"] == "other"
    assert result["declarations"][0]["reason"] == reason


@pytest.mark.parametrize(
    "members",
    [
        [["aws_s3_bucket", "main"]],
        [("aws_s3_bucket", "main")],
    ],
)
def test_f_sametype_joins_type_and_parsed_key_not_bare_key(members):
    pending = pending_scope([declaration(), declaration("aws_db_instance")])
    result = scope_api().finalize_scope(pending, members, "completed")
    assert [(d["category"], d["reason"]) for d in result["declarations"]] == [
        ("reviewed", None),
        ("other", "summary_cap"),
    ]
    assert result["x"] == result["sent_count"] == 1


def test_join_uses_captured_collision_key_not_module_address():
    pending = pending_scope(
        [
            declaration(key="unit/main", address="module.web.aws_s3_bucket.main"),
            declaration(
                key="jobs_1/unit/main", address="module.jobs.aws_s3_bucket.main"
            ),
        ]
    )
    result = scope_api().finalize_scope(
        pending, [["aws_s3_bucket", "jobs_1/unit/main"]], "completed"
    )
    assert [d["in_summary"] for d in result["declarations"]] == [False, True]
    assert result["x"] == 1


@pytest.mark.parametrize("outcome", ["completed", "not_invoked", "unknown"])
def test_finalize_never_mutates_input_or_nested_lists(outcome):
    pending = pending_scope(
        [declaration()],
        gaps=[{"address": "module.remote", "reasons": ["remote_source"]}],
    )
    pending["warnings"] = ["skipped_tf_json"]
    pending["count_complete"] = False
    before = deepcopy(pending)
    members = [["aws_s3_bucket", "main"]]
    result = scope_api().finalize_scope(pending, members, outcome)
    assert pending == before
    assert result is not pending
    assert members == [["aws_s3_bucket", "main"]]


@pytest.mark.parametrize("state", ["unknown_root", "malformed"])
@pytest.mark.parametrize("outcome", ["completed", "not_invoked", "unknown"])
def test_nonrecorded_states_never_turn_unknown_counts_into_zero(state, outcome):
    pending = pending_scope(state=state)
    assert scope_api().validate_scope(pending) == []
    result = scope_api().finalize_scope(pending, None, outcome)
    assert result["state"] == state
    assert result["status"] == "final"
    assert result["model_outcome"] == outcome
    assert result["known_y"] is result["x"] is result["sent_count"] is None
    assert result["declarations"] == []
    assert result["categories"] == pending["categories"]
    assert scope_api().validate_scope(result) == []


def test_full_serialized_final_record_validates_and_matches_finalize():
    expected = json.loads(json.dumps(completed_scope()))
    assert scope_api().validate_scope(expected) == []
    actual = scope_api().finalize_scope(
        pending_scope([declaration()]), [["aws_s3_bucket", "main"]], "completed"
    )
    assert json.loads(json.dumps(actual)) == expected


@pytest.mark.parametrize("size,valid", [(1000, True), (1001, False)])
def test_declaration_validation_bound(size, valid):
    record = pending_scope([declaration(key=f"b{i}") for i in range(size)])
    assert (scope_api().validate_scope(record) == []) is valid


@pytest.mark.parametrize("size,valid", [(100, True), (101, False)])
def test_gap_validation_bound(size, valid):
    record = pending_scope(
        gaps=[
            {"address": f"module.m{i}", "reasons": ["remote_source"]}
            for i in range(size)
        ]
    )
    assert (scope_api().validate_scope(record) == []) is valid


@pytest.mark.parametrize(
    "reason",
    [
        "remote_source",
        "source_unresolved",
        "source_missing",
        "source_outside_archive",
        "count_unresolved",
        "count_not_singleton",
        "for_each_unsupported",
        "cycle",
        "depth_limit",
        "expansion_limit",
    ],
)
def test_gap_reason_enum_accepts_contract_values(reason):
    record = pending_scope(gaps=[{"address": "module.child", "reasons": [reason]}])
    assert scope_api().validate_scope(record) == []


@pytest.mark.parametrize(
    "key,value",
    [
        ("version", "review_scope@2"),
        ("status", "done"),
        ("state", "invented"),
        ("known_y", True),
        ("known_y", -1),
        ("known_y", 2),
        ("x", 0),
        ("sent_count", 0),
        ("count_complete", "true"),
        ("gaps_complete", 1),
        ("model_outcome", "pending"),
        ("declarations", {}),
        ("categories", {"reviewed": 0, "zero_copy": 0, "unsupported": 0, "other": 0}),
    ],
)
def test_validator_rejects_invalid_final_types_enums_and_counts(key, value):
    record = completed_scope()
    record[key] = value
    assert scope_api().validate_scope(record)


@pytest.mark.parametrize(
    "key,value",
    [
        ("instances", True),
        ("instances", -1),
        ("instances", 1001),
        ("retained", "true"),
        ("in_summary", None),
        ("sent", None),
        ("category", None),
        ("category", "invented"),
        ("reason", "invented"),
        ("address", "aws_s3_bucket.bad/name"),
        ("address", "a" * 513),
    ],
)
def test_validator_rejects_invalid_declaration(key, value):
    record = completed_scope()
    record["declarations"][0][key] = value
    assert scope_api().validate_scope(record)


@pytest.mark.parametrize(
    "key,value", [("model_outcome", "completed"), ("x", 0), ("sent_count", 0)]
)
def test_pending_cannot_claim_final_outcomes(key, value):
    record = pending_scope([declaration()])
    record[key] = value
    assert scope_api().validate_scope(record)


@pytest.mark.parametrize(
    "key,value",
    [
        ("in_summary", False),
        ("sent", False),
        ("category", "reviewed"),
        ("reason", "summary_cap"),
    ],
)
def test_pending_cannot_claim_final_declaration_results(key, value):
    record = pending_scope([declaration()])
    record["declarations"][0][key] = value
    assert scope_api().validate_scope(record)


@pytest.mark.parametrize("record", [None, [], "bad", {}, {"version": "review_scope@1"}])
def test_validate_scope_never_raises_for_malformed_input(record):
    errors = scope_api().validate_scope(record)
    assert isinstance(errors, list) and errors
