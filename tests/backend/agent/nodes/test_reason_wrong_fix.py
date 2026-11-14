"""The reasoning step drops a wrong fix and keeps its valid siblings (P1 E1),
and its prompt states the retention rule (P1 E2)."""

from backend.agent.nodes.reason import SYSTEM_PROMPT, rejection_kind, verify_model_findings
from tests.backend.agent.nodes.test_reason import _chunk, _valid_finding_item

_CHUNK = _chunk("chunk-a", "Encrypt data at rest using AWS KMS customer managed keys.")


def _verify(items):
    return verify_model_findings(items, "r1", "fake-model", "corpus@1", [_CHUNK], None)


def test_a_vpc_fix_for_a_function_url_is_rejected_as_a_wrong_fix_and_siblings_survive():
    wrong = _valid_finding_item(
        finding="The Lambda has a public function URL and runs outside any VPC.",
        recommendation="Attach the function to the workload VPC and add a VPC endpoint.",
    )
    findings, failures = _verify([wrong, _valid_finding_item()])
    assert len(findings) == 1
    assert [rejection_kind(f) for f in failures] == ["wrong_fix"]


def test_a_correct_function_url_fix_is_kept():
    right = _valid_finding_item(
        finding="The Lambda has a public function URL with no authentication.",
        recommendation="Require AWS_IAM authorization or remove the URL.",
    )
    findings, failures = _verify([right])
    assert len(findings) == 1 and failures == []


def test_the_prompt_states_that_a_met_retention_window_is_correct():
    prompt = " ".join(SYSTEM_PROMPT.split())
    assert "never recommend removing, shortening or disabling it" in prompt
