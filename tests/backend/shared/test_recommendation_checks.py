"""A wrong fix for a public Lambda URL is caught (P1 defect E1).

Found in the P1 baseline (slot 1): a function-URL finding recommended
attaching the function to a VPC, which does not restrict a function URL and
can cut the function's outbound access.
"""

import pytest

from backend.shared.recommendation_checks import recommends_vpc_for_function_url
from tests.backend.p1_guards import load_recorded

_URL = "The contractor_export Lambda has a public function URL with no authentication."


@pytest.mark.parametrize(
    "recommendation",
    [
        "Attach aws_lambda_function.contractor_export to the workload VPC and a private subnet.",
        "Move the function into a VPC, then add a Lambda VPC endpoint.",
        "Place it in a private VPC; this adds a network boundary.",
    ],
)
def test_a_vpc_fix_for_a_function_url_is_flagged(recommendation):
    assert recommends_vpc_for_function_url(_URL, recommendation)


@pytest.mark.parametrize(
    ("finding", "recommendation"),
    [
        (_URL, "Require AWS_IAM authorization or remove the URL and its public permissions."),
        (_URL, "Placing the function in a VPC does not restrict a function URL."),
        (_URL, "Remove the URL. A VPC cannot restrict a function URL, so do not rely on one."),
        (
            "An RDS instance is reachable from the internet.",
            "Move the instance into a private VPC subnet.",
        ),
        ("", ""),
    ],
    ids=["right-fix", "says-vpc-does-not-help", "negated", "other-resource", "empty"],
)
def test_correct_or_unrelated_recommendations_are_not_flagged(finding, recommendation):
    assert not recommends_vpc_for_function_url(finding, recommendation)


def test_the_recorded_slot_1_finding_is_flagged():
    finding = next(
        f for f in load_recorded(1)["findings"] if f["finding_id"].startswith("96c9681b")
    )
    assert recommends_vpc_for_function_url(
        " ".join([finding["finding"], finding["evidence"]]), finding["recommendation"]
    )


def test_the_deterministic_rules_own_fix_is_not_flagged():
    """The new public_lambda_url finding tells the owner a VPC does not help;
    it must never trip its own check."""
    from backend.shared.configuration_checks import ConfigurationIssue  # noqa: F401
    import tempfile
    from dataclasses import asdict
    from pathlib import Path

    from backend.lambdas.ingest.handler import parse_terraform_files
    from backend.lambdas.rule_engine.handler import run_rules

    source = Path(tempfile.mkdtemp()) / "main.tf"
    source.write_text(
        'resource "aws_lambda_function" "fn" { function_name = "fn" role = "r" handler = "h" runtime = "python3.12" }\n'
        'resource "aws_lambda_function_url" "fn" { function_name = aws_lambda_function.fn.function_name\n authorization_type = "NONE" }\n'
        'resource "aws_lambda_permission" "u" { statement_id = "u" action = "lambda:InvokeFunctionUrl" function_name = aws_lambda_function.fn.function_name principal = "*" function_url_auth_type = "NONE" }\n'
        'resource "aws_lambda_permission" "i" { statement_id = "i" action = "lambda:InvokeFunction" function_name = aws_lambda_function.fn.function_name principal = "*" invoked_via_function_url = true }\n',
        encoding="utf-8",
    )
    found = [
        f
        for f in run_rules(asdict(parse_terraform_files([str(source)])), "r")
        if f.concern == "public_lambda_url"
    ]
    assert len(found) == 1
    assert not recommends_vpc_for_function_url(
        found[0].finding + " " + found[0].evidence, found[0].recommendation
    )
