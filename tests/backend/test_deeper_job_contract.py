"""Prevent timeout, paid-retry and content-boundary regressions in deployment."""

from pathlib import Path

import hcl2
from hcl2.utils import SerializationOptions

from backend.lambdas.deeper_review.worker import AGENT_READ_TIMEOUT_SECONDS
from backend.shared.deeper_jobs import JOB_LIFETIME_SECONDS
from backend.shared.hcl_eval import resolve

MODULE = Path(__file__).resolve().parents[2] / "infra/modules/api-gateway"


def resources(name):
    parsed = hcl2.loads(
        (MODULE / name).read_text(),
        serialization_options=SerializationOptions(strip_string_quotes=True),
    )
    merged = {}
    for item in parsed.get("resource", []):
        for kind, values in item.items():
            merged.setdefault(kind, {}).update(values)
    return parsed, merged


def test_deeper_model_runs_outside_http_under_a_bounded_standard_workflow():
    _, jobs = resources("deeper-jobs.tf")
    _, api = resources("main.tf")
    machine = jobs["aws_sfn_state_machine"]["deeper"]
    definition = resolve(machine["definition"], {})
    assert machine["type"] == "STANDARD"
    worker = jobs["aws_lambda_function"]["deeper_worker"]
    assert worker["handler"] == "backend.lambdas.deeper_review.worker.run_job"
    assert api["aws_lambda_function"]["deeper_review"]["timeout"] < 29
    assert (
        AGENT_READ_TIMEOUT_SECONDS
        < worker["timeout"]
        < definition["States"]["Run"]["TimeoutSeconds"]
        < definition["TimeoutSeconds"]
        < JOB_LIFETIME_SECONDS
    )


def test_deeper_workflow_never_retries_paid_work_or_passes_customer_content():
    _, jobs = resources("deeper-jobs.tf")
    machine = jobs["aws_sfn_state_machine"]["deeper"]
    definition = resolve(machine["definition"], {})
    for task in definition["States"].values():
        assert "Retry" not in task
        assert set(task["Parameters"]) == {
            "review_id.$",
            "finding_id.$",
            "job_id.$",
            "phase",
        }
        assert task["ResultPath"] is None
    assert definition["States"]["Run"]["Catch"][0]["Next"] == "MarkFailed"
    assert definition["States"]["Run"]["Catch"][0]["ResultPath"] is None
    assert machine["logging_configuration"][0]["include_execution_data"] is False


def test_http_role_cannot_invoke_the_model_and_worker_can_decrypt_the_report():
    parsed, _ = resources("main.tf")
    policy = next(
        item["aws_iam_policy_document"]["deeper_review_data_access"]
        for item in parsed["data"]
        if "deeper_review_data_access" in item.get("aws_iam_policy_document", {})
    )
    actions = {
        action for statement in policy["statement"] for action in statement["actions"]
    }
    assert "states:StartExecution" in actions
    assert "bedrock-agentcore:InvokeAgentRuntime" not in actions
    _, encryption = resources("storage-key.tf")
    grant = encryption["aws_iam_role_policy"]["admission_storage_key"]
    assert "deeper_worker" in grant["for_each"]
