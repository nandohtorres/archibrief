import json

import backend.lambdas.finalize.handler as handler_module
from backend.lambdas.finalize.handler import (
    assemble_baseline_answers,
    assemble_evidence_ledger,
    compute_cost_estimate_tier,
    handler,
)
from backend.shared.models.finding import (
    ConfidenceInputs,
    DepthLevel,
    Finding,
    FindingCategory,
    FindingType,
)


class _FakeDynamoDBClient:
    def __init__(self, table_name: str):
        self.table_name = table_name

    def get_item(self, key: dict) -> dict | None:
        return _FakeDynamoDBClient.ITEMS.get(key["reviewId"])

    def put_item(self, item: dict) -> None:
        _FakeDynamoDBClient.ITEMS[item["reviewId"]] = item

    ITEMS: dict = {}


def _finding(**overrides) -> Finding:
    defaults = dict(
        finding_id="f1",
        review_id="r1",
        category=FindingCategory.IAM,
        type=FindingType.NOT_OBSERVABLE,
        finding="finding text",
        evidence="evidence text",
        citation=None,
        confidence=0.5,
        confidence_inputs=ConfidenceInputs(
            evidence_directness=0.5, source_agreement=0.5, rule_determinism=0.5
        ),
        risk_impact="low",
        recommendation="do nothing",
        framework_mapping=[],
        depth_level=DepthLevel.LIGHTWEIGHT,
    )
    defaults.update(overrides)
    return Finding(**defaults)


def test_assemble_evidence_ledger_includes_workload_brief():
    ledger = assemble_evidence_ledger(
        "r1", [_finding()], workload_brief="a 3-tier web app on ECS"
    )
    assert ledger["workload_brief"] == "a 3-tier web app on ECS"


def test_assemble_evidence_ledger_defaults_workload_brief_to_none():
    ledger = assemble_evidence_ledger("r1", [_finding()])
    assert ledger["workload_brief"] is None


def test_handler_passes_workload_brief_through_to_ledger():
    event = {
        "review_id": "r1",
        "findings": [_finding().model_dump(mode="json")],
        "workload_brief": "a 3-tier web app on ECS",
    }
    result = handler(event, None)
    assert result["status"] == "complete"


def test_handler_merges_pointer_item_instead_of_replacing_it(monkeypatch):
    # DynamoDB's PutItem replaces the whole item, unlike UpdateItem — a
    # pointer_item built from scratch here would wipe out whatever
    # IdempotencyGate already wrote earlier in the same execution
    # (terraformRepoRef, idempotencyKey, createdAt), so the handler must
    # fetch and merge.
    monkeypatch.setattr(handler_module, "DynamoDBClient", _FakeDynamoDBClient)
    _FakeDynamoDBClient.ITEMS = {
        "r1": {
            "reviewId": "r1",
            "idempotencyKey": "r1",
            "status": "pending",
            "createdAt": "2026-10-01T00:00:00Z",
            "terraformRepoRef": "github.com/example/infra",
        }
    }

    event = {
        "review_id": "r1",
        "findings": [_finding().model_dump(mode="json")],
        "reviews_table_name": "archibrief-dev-reviews",
    }
    result = handler(event, None)

    assert result["status"] == "complete"
    stored = _FakeDynamoDBClient.ITEMS["r1"]
    assert stored["status"] == "complete"
    assert stored["terraformRepoRef"] == "github.com/example/infra"
    assert stored["idempotencyKey"] == "r1"
    assert stored["createdAt"] == "2026-10-01T00:00:00Z"
    from backend.shared.retention import review_expires_at

    assert stored["ttl"] == review_expires_at({"createdAt": stored["createdAt"]})
    assert "reportS3Key" in stored


def test_handler_creates_pointer_item_when_none_exists_yet(monkeypatch):
    monkeypatch.setattr(handler_module, "DynamoDBClient", _FakeDynamoDBClient)
    _FakeDynamoDBClient.ITEMS = {}

    event = {
        "review_id": "r2",
        "findings": [_finding().model_dump(mode="json")],
        "reviews_table_name": "archibrief-dev-reviews",
    }
    result = handler(event, None)

    assert result["status"] == "complete"
    assert _FakeDynamoDBClient.ITEMS["r2"]["reviewId"] == "r2"
    assert _FakeDynamoDBClient.ITEMS["r2"]["status"] == "complete"


def test_compute_cost_estimate_tier_low_for_a_handful_of_resources():
    resources = {"aws_s3_bucket": {"a": {}, "b": {}}}
    assert compute_cost_estimate_tier(resources) == "low"


def test_compute_cost_estimate_tier_medium_for_dozens_of_resources():
    resources = {"aws_lambda_function": {f"fn{i}": {} for i in range(10)}}
    assert compute_cost_estimate_tier(resources) == "medium"


def test_compute_cost_estimate_tier_high_for_many_resources():
    resources = {"aws_lambda_function": {f"fn{i}": {} for i in range(25)}}
    assert compute_cost_estimate_tier(resources) == "high"


def test_compute_cost_estimate_tier_counts_across_every_resource_type():
    # 3 + 3 = 6 total resource instances, summed across both types —
    # over the low-tier threshold even though each individual type's
    # count alone would stay under it.
    resources = {
        "aws_s3_bucket": {f"b{i}": {} for i in range(3)},
        "aws_lambda_function": {f"fn{i}": {} for i in range(3)},
    }
    assert compute_cost_estimate_tier(resources) == "medium"


def test_compute_cost_estimate_tier_defaults_low_for_no_resources():
    assert compute_cost_estimate_tier(None) == "low"
    assert compute_cost_estimate_tier({}) == "low"


def test_handler_persists_computed_cost_estimate_tier(monkeypatch):
    monkeypatch.setattr(handler_module, "DynamoDBClient", _FakeDynamoDBClient)
    _FakeDynamoDBClient.ITEMS = {}

    event = {
        "review_id": "r3",
        "findings": [_finding().model_dump(mode="json")],
        "reviews_table_name": "archibrief-dev-reviews",
        "resources": {"aws_lambda_function": {f"fn{i}": {} for i in range(25)}},
    }
    handler(event, None)

    assert _FakeDynamoDBClient.ITEMS["r3"]["costEstimateTier"] == "high"


def test_assemble_baseline_answers_maps_preflight_field_state_to_contract_shape():
    preflight_fields = {
        "expected_traffic_scale": {
            "outcome": "assumption",
            "value": "low-to-moderate",
            "is_assumption": True,
        },
        "regulatory_data_residency": {
            "outcome": "answered",
            "value": "EU only",
            "is_assumption": False,
        },
    }

    answers = assemble_baseline_answers(
        preflight_fields, "preflight_defaults@2026-09-08"
    )

    by_field = {a["field"]: a for a in answers}
    assert by_field["expected_traffic_scale"]["label"] == "Traffic and scale"
    assert by_field["expected_traffic_scale"]["outcome"] == "assumption"
    assert by_field["expected_traffic_scale"]["value"] == "low-to-moderate"
    assert (
        by_field["expected_traffic_scale"]["policy_version"]
        == "preflight_defaults@2026-09-08"
    )
    assert by_field["regulatory_data_residency"]["outcome"] == "answered"


def test_assemble_baseline_answers_maps_unknown_and_paused_to_not_observable():
    preflight_fields = {
        "a": {"outcome": "unknown", "value": None, "is_assumption": False},
        "b": {"outcome": "paused", "value": None, "is_assumption": False},
    }

    answers = assemble_baseline_answers(preflight_fields, None)

    outcomes = {a["field"]: a["outcome"] for a in answers}
    assert outcomes == {"a": "not-observable", "b": "not-observable"}


def test_assemble_evidence_ledger_includes_baseline_answers():
    ledger = assemble_evidence_ledger(
        "r1",
        [_finding()],
        baseline_answers=[
            {
                "field": "x",
                "label": "X",
                "outcome": "answered",
                "value": "y",
                "policy_version": "v1",
            }
        ],
    )
    assert ledger["baseline_answers"][0]["field"] == "x"


def test_handler_persists_baseline_answers_from_preflight_fields():
    event = {
        "review_id": "r1",
        "findings": [_finding().model_dump(mode="json")],
        "preflight_fields": {
            "expected_traffic_scale": {
                "outcome": "assumption",
                "value": "low",
                "is_assumption": True,
            }
        },
        "defaults_version": "preflight_defaults@2026-09-08",
    }
    result = handler(event, None)
    assert result["status"] == "complete"


def test_cost_tier_uses_resource_count_when_resources_are_not_in_state():
    assert compute_cost_estimate_tier(None, resource_count=3) == "low"
    assert compute_cost_estimate_tier(None, resource_count=12) == "medium"
    assert compute_cost_estimate_tier(None, resource_count=40) == "high"


def test_ledger_keeps_the_resource_summary_for_the_chat():
    # ADR-0050: the report chat answers from the same summary Reason saw.
    summary = {"resources": [{"type": "aws_s3_bucket", "name": "logs", "settings": {}}]}
    ledger = assemble_evidence_ledger("r1", [_finding()], terraform_resources=summary)
    assert ledger["terraform_resources"] == summary
    assert assemble_evidence_ledger("r1", [_finding()])["terraform_resources"] is None


def test_handler_stores_the_resource_summary_from_the_event(monkeypatch):
    written = {}

    class FakeS3:
        def __init__(self, bucket):
            pass

        def put_object(self, key, body):
            written["ledger"] = json.loads(body)

    monkeypatch.setattr("backend.lambdas.finalize.handler.S3Client", FakeS3)
    summary = {"resources": [], "truncated": False, "note": "n"}
    handler(
        {
            "review_id": "r1",
            "findings": [_finding().model_dump(mode="json")],
            "terraform_resources": summary,
            "report_bucket": "reports",
        },
        None,
    )
    assert written["ledger"]["terraform_resources"] == summary


def _graph() -> dict:
    return {
        "version": 1,
        "lanes": ["data"],
        "nodes": [
            {
                "id": "aws_s3_bucket.card-data-bucket",
                "type": "aws_s3_bucket",
                "label": "s3 bucket",
                "name": "card-data-bucket",
                "module": "",
                "lane": "data",
                "details": [],
                "findings": [],
            }
        ],
        "edges": [],
        "account_findings": [],
        "truncated": False,
    }


def _run_finalize(monkeypatch, event: dict) -> dict:
    written = {}

    class FakeS3:
        def __init__(self, bucket):
            pass

        def put_object(self, key, body):
            written["ledger"] = json.loads(body)

    monkeypatch.setattr("backend.lambdas.finalize.handler.S3Client", FakeS3)
    handler({"review_id": "r1", "report_bucket": "reports", **event}, None)
    return written["ledger"]


def test_handler_places_the_final_findings_on_the_architecture(monkeypatch):
    findings = [
        _finding(
            finding_id="on-bucket", finding="Bucket 'card-data-bucket' is not encrypted"
        ),
        _finding(finding_id="account", finding="No aws_cloudtrail resource found"),
    ]
    ledger = _run_finalize(
        monkeypatch,
        {
            "findings": [f.model_dump(mode="json") for f in findings],
            "architecture": _graph(),
        },
    )
    graph = ledger["architecture"]
    assert graph["nodes"][0]["findings"] == ["on-bucket"]
    assert graph["account_findings"] == ["account"]


def test_handler_without_a_graph_stores_no_architecture(monkeypatch):
    for event in ({}, {"architecture": None}, {"architecture": "not a graph"}):
        ledger = _run_finalize(
            monkeypatch, {"findings": [_finding().model_dump(mode="json")], **event}
        )
        assert "architecture" not in ledger
