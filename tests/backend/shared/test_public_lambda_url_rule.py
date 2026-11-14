"""A public Lambda function URL is reported (P1 defect A, audit F07-D-03).

Found in the P1 baseline: two of three runs missed a function URL with no
authentication, because only the model could flag it. The facts already
reached the model; this makes the finding deterministic.
"""

import tempfile
from dataclasses import asdict
from pathlib import Path

import pytest

from backend.lambdas.ingest.handler import parse_terraform_files
from backend.lambdas.rule_engine.handler import run_rules
from backend.shared.stakeholder.catalog import RECIPES

_BASE = """
resource "aws_lambda_function" "fn" {
  function_name = "fn"
  role          = "arn:aws:iam::123456789012:role/r"
  handler       = "h"
  runtime       = "python3.12"
}
"""
_URL = 'resource "aws_lambda_function_url" "fn" { function_name = aws_lambda_function.fn.function_name\n  authorization_type = "%s" }\n'
_URL_PERMISSION = """
resource "aws_lambda_permission" "%s" {
  statement_id  = "%s"
  action        = "%s"
  function_name = aws_lambda_function.fn.function_name
  principal     = "%s"
  %s
}
"""


def _concerns(source: str) -> list[str]:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "main.tf"
        path.write_text(source, encoding="utf-8")
        parsed = asdict(parse_terraform_files([str(path)]))
    return [f.concern for f in run_rules(parsed, "r") if f.concern == "public_lambda_url"]


def _public(auth: str = "NONE", principal: str = "*") -> str:
    return (
        _BASE
        + _URL % auth
        + _URL_PERMISSION
        % (
            "url",
            "PublicUrl",
            "lambda:InvokeFunctionUrl",
            principal,
            'function_url_auth_type = "NONE"',
        )
        + _URL_PERMISSION
        % (
            "invoke",
            "PublicInvoke",
            "lambda:InvokeFunction",
            principal,
            "invoked_via_function_url = true",
        )
    )


def test_an_open_function_url_with_public_permissions_is_reported_once():
    assert _concerns(_public()) == ["public_lambda_url"]


@pytest.mark.parametrize(
    ("source", "why"),
    [
        (_public(auth="AWS_IAM"), "IAM-authenticated URL"),
        (_BASE, "no URL at all"),
        (_BASE + _URL % "NONE", "NONE auth but no public invoke permissions"),
        (_public(principal="123456789012"), "permissions limited to one account"),
    ],
    ids=["aws-iam", "no-url", "no-permissions", "account-principal"],
)
def test_safe_declarations_are_not_reported(source, why):
    assert _concerns(source) == [], why


def test_the_concern_has_a_high_severity_recipe_for_ranking():
    assert RECIPES["public_lambda_url"].severity == "high"
