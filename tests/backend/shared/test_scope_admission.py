import copy
import time
from types import SimpleNamespace

import boto3
import pytest
from moto import mock_aws

from backend.shared import scope_admission as admission
from backend.shared.admission import AdmissionDenied, request_digest
from backend.shared.clients import BedrockEmbeddingClient
from backend.shared.review_scope import finalize_scope
from tests.backend.p0_scope_fixtures import declaration, pending_scope


@pytest.fixture
def operation(monkeypatch):
    with mock_aws():
        monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
        monkeypatch.setenv("USAGE_COUNTERS_TABLE_NAME", "scope-test")
        table = boto3.resource("dynamodb", region_name="us-east-1").create_table(
            TableName="scope-test", KeySchema=[{"AttributeName": "counterKey", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "counterKey", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        review = {
            "reviewId": "review-1", "ttl": int(time.time()) + 1000,
            "archiveSha256": "a" * 64, "archiveVersionId": "archive-version",
            "inputDigest": request_digest({"submission": "fixture"}),
        }
        table.put_item(Item={
            "counterKey": "operation#review-1#initial", "digest": review["inputDigest"],
            "ttl": review["ttl"], "cost": 400000,
        })
        scope = pending_scope([declaration()])
        payload = {"review_id": "review-1", "terraform_resources": {"resources": []}}
        bound = admission.prepare_operation(review, scope, payload, operation="initial", job_id="review-1")
        from backend.shared.model_request_budget import MAX_REQUEST_BYTES, MAX_EVIDENCE_BYTES, POLICY_VERSION
        admission.record_request_envelope(bound, {
            "version": POLICY_VERSION, "max_request_bytes": MAX_REQUEST_BYTES,
            "max_evidence_bytes": MAX_EVIDENCE_BYTES, "request_bound_bytes": 50000,
            "input_token_bound": 45000, "cost_bound_micro_usd": 380000,
        })
        context = admission.claim_input_screen(bound)
        admission.finish_input_screen(context, True)
        yield SimpleNamespace(table=table, review=review, scope=scope, payload=payload, bound=bound)


def test_exact_payload_authorizes_with_consistent_reads_and_no_public_counts(operation, monkeypatch):
    calls = []
    original = admission.DynamoDBClient.get_item

    def read(self, key, **kwargs):
        calls.append(kwargs)
        return original(self, key, **kwargs)

    monkeypatch.setattr(admission.DynamoDBClient, "get_item", read)
    context = admission.authorize_payload(operation.bound)
    assert context.review_id == "review-1"
    assert calls == [{"consistent": True}]
    assert "known_y" not in operation.bound["review_scope_ref"]


@pytest.mark.parametrize("field,value", [
    ("terraform_resources", {"resources": [{"type": "aws_s3_bucket"}]}),
    ("review_id", "other"), ("max_tokens", 999999), ("mode", "deeper"),
    ("review_scope_ref", {"operation": "initial", "job_id": "wrong"}),
    ("review_scope_ref", {"operation": "initial", "job_id": "review-1", "known_y": 1}),
])
def test_forged_payload_or_reference_is_not_admitted(operation, field, value):
    payload = {**operation.bound, field: value}
    with pytest.raises(AdmissionDenied):
        admission.authorize_payload(payload)


@pytest.mark.parametrize("field,value", [
    ("released", True), ("ttl", 1), ("cost", 400001),
    ("runtime_payload_sha256", "0" * 64),
])
def test_released_expired_overbudget_or_rebound_receipt_stops_dispatch(operation, field, value):
    key = {"counterKey": "operation#review-1#initial"}
    row = operation.table.get_item(Key=key)["Item"]
    row[field] = value
    operation.table.put_item(Item=row)
    with pytest.raises(AdmissionDenied):
        admission.authorize_payload(operation.bound)


@pytest.mark.parametrize("field,value", [
    ("known_y", 51), ("known_y", True), ("known_y", -1),
    ("policy_version", "old"), ("version", "old"), ("root_id", "nested"),
    ("expires_at_epoch_s", 1), ("archive_sha256", "bad"),
    ("inventory_sha256", "bad"), ("archive_version_id", "null"),
    ("total_complete", "true"), ("operation", "deeper:other"),
])
def test_malformed_stored_admission_stops_dispatch(operation, field, value):
    key = {"counterKey": "operation#review-1#initial"}
    row = operation.table.get_item(Key=key)["Item"]
    row["scope_admission"][field] = value
    operation.table.put_item(Item=row)
    with pytest.raises(AdmissionDenied):
        admission.authorize_payload(operation.bound)


def test_pending_and_final_inventory_binding_agree_and_deeper_requires_parent(operation):
    final = finalize_scope(operation.scope, [["aws_s3_bucket", "main"]], "completed")
    assert admission.inventory_digest(final) == admission.inventory_digest(operation.scope)
    assert admission.eligible_parent("review-1", final)["known_y"] == 1
    deeper = {"review_id": "review-1", "mode": "deeper", "parent_finding_id": "f1"}
    operation.table.put_item(Item={
        "counterKey": "operation#review-1#deeper:f1", "digest": request_digest({"finding_id": "f1"}),
        "ttl": operation.review["ttl"], "cost": 200000,
    })
    bound = admission.prepare_operation(operation.review, final, deeper, operation="deeper:f1", job_id="job-1")
    assert admission.authorize_payload(bound).operation == "deeper:f1"
    final["declarations"][0]["address"] = "aws_s3_bucket.changed"
    with pytest.raises(AdmissionDenied):
        admission.eligible_parent("review-1", final)


def test_direct_node_real_adapter_requires_context_and_rechecks_release(operation):
    client = object.__new__(BedrockEmbeddingClient)
    with pytest.raises(AdmissionDenied):
        admission.check_paid_scope({"review_id": "review-1"}, client)
    with pytest.raises(AdmissionDenied):
        admission.check_paid_scope({"review_id": "review-1", "paid_scope_context": {"authorized": True}}, client)
    state = {"review_id": "review-1", "paid_scope_context": admission.authorize_payload(operation.bound)}
    from backend.shared.model_request_budget import GenerationBudget
    with pytest.raises(AdmissionDenied, match="budget_unavailable"):
        admission.check_paid_scope(state, client)
    state["generation_budget"] = GenerationBudget("initial", 400000, time.monotonic() + 100)
    admission.check_paid_scope(state, client)
    operation.table.update_item(Key={"counterKey": "operation#review-1#initial"}, UpdateExpression="SET released = :yes", ExpressionAttributeValues={":yes": True})
    with pytest.raises(AdmissionDenied):
        admission.check_paid_scope(state, client)


def test_unknown_and_oversized_scopes_cannot_be_prepared(operation):
    before = copy.deepcopy(operation.bound)
    for scope in (None, {}, pending_scope([declaration(key=f"r{n}") for n in range(51)])):
        with pytest.raises(AdmissionDenied):
            admission.prepare_operation(operation.review, scope, operation.payload, operation="initial", job_id="review-1")
    assert operation.bound == before
