"""P0 rule-engine handoff: membership is private and uses typed parsed keys."""

import json
from copy import deepcopy

from backend.lambdas.rule_engine import handler as rules
from backend.lambdas.rule_engine.resource_summary import build_resource_summary
from tests.backend.p0_scope_fixtures import declaration, pending_scope, scope_api


def _run(resources, declarations):
    pending = pending_scope(declarations)
    parsed = {"resources": resources, "review_scope": pending}
    before = deepcopy(parsed)
    result = rules.handler({"review_id": "p0", "parsed": parsed}, None)
    assert result["resource_summary"] == build_resource_summary(before)
    assert "review_scope" not in result["resource_summary"]
    assert "summary_members" not in result["resource_summary"]
    assert result["review_scope"] == pending
    assert parsed == before
    return result


def test_f_cap_records_121_declarations_and_120_members():
    resources = {"aws_s3_bucket": {f"b{i:03d}": {} for i in range(121)}}
    response = _run(
        resources, [declaration(key=key) for key in resources["aws_s3_bucket"]]
    )
    members = response["summary_members"]
    assert len(members) == len({tuple(pair) for pair in members}) == 120
    assert {tuple(pair) for pair in members} == {
        ("aws_s3_bucket", f"b{i:03d}") for i in range(120)
    }
    final = scope_api().finalize_scope(response["review_scope"], members, "completed")
    assert (final["known_y"], final["x"]) == (121, 120)
    omitted = [d for d in final["declarations"] if not d["in_summary"]]
    assert len(omitted) == 1
    assert (omitted[0]["category"], omitted[0]["reason"]) == ("other", "summary_cap")


def test_f_sametype_real_cap_does_not_join_different_types_with_same_key():
    # Both scored types have equal priority; each type's first entry wins
    # before its second. Earlier buckets keep S3 main outside the cap.
    resources = {
        "aws_db_instance": {"main": {}},
        "aws_s3_bucket": {**{f"a{i:03d}": {} for i in range(120)}, "main": {}},
    }
    declarations = [
        declaration(kind, key) for kind, entries in resources.items() for key in entries
    ]
    response = _run(resources, declarations)
    members = {tuple(pair) for pair in response["summary_members"]}
    assert ("aws_db_instance", "main") in members
    assert ("aws_s3_bucket", "main") not in members
    final = scope_api().finalize_scope(
        response["review_scope"], response["summary_members"], "completed"
    )
    named = {d["type"]: d for d in final["declarations"] if d["parsed_key"] == "main"}
    assert named["aws_db_instance"]["category"] == "reviewed"
    assert named["aws_s3_bucket"]["reason"] == "summary_cap"


def test_members_include_nonaws_but_exclude_zero_and_filtered_types():
    resources = {
        "aws_s3_bucket": {"main": {}, "off": {"count": 0}},
        "random_id": {"id": {}},
        "aws_Custom": {"main": {}},
    }
    declarations = [
        declaration(),
        declaration(key="off", instances=0),
        declaration("random_id", "id"),
        declaration("aws_Custom"),
    ]
    response = _run(resources, declarations)
    assert {tuple(pair) for pair in response["summary_members"]} == {
        ("aws_s3_bucket", "main"),
        ("random_id", "id"),
    }


def test_members_keep_private_scoped_keys_instead_of_display_names():
    keys = ["unit/main", "jobs_1/unit/main"]
    response = _run(
        {"aws_s3_bucket": {key: {} for key in keys}},
        [
            declaration(key=key, address=f"module.{call}.aws_s3_bucket.main")
            for key, call in zip(keys, ["web", "jobs"])
        ],
    )
    assert {tuple(pair) for pair in response["summary_members"]} == {
        ("aws_s3_bucket", key) for key in keys
    }


def test_s3_handoff_returns_pending_scope_unchanged(monkeypatch):
    pending = pending_scope([declaration()])
    pending["warnings"] = ["skipped_tf_json"]
    pending["count_complete"] = False
    payload = {"resources": {"aws_s3_bucket": {"main": {}}}, "review_scope": pending}

    class Storage:
        def __init__(self, bucket):
            assert bucket == "reports"

        def get_object(self, key):
            assert key == "parsed/p0.json"
            return json.dumps(payload).encode()

    monkeypatch.setattr(rules, "S3Client", Storage)
    result = rules.handler(
        {
            "review_id": "p0",
            "parsed_s3_key": "parsed/p0.json",
            "report_bucket": "reports",
        },
        None,
    )
    assert result["review_scope"] == pending
    assert result["review_scope"]["status"] == "pending"
    assert result["summary_members"] == [["aws_s3_bucket", "main"]]


def test_legacy_parsed_input_returns_none_scope_and_still_reports_members():
    result = rules.handler(
        {"review_id": "p0", "parsed": {"resources": {"aws_s3_bucket": {"main": {}}}}},
        None,
    )
    assert result["review_scope"] is None
    assert result["summary_members"] == [["aws_s3_bucket", "main"]]
