"""Handler fallbacks must match the Terraform defaults.

Terraform sets these values on every deployed Lambda; the handler fallbacks
apply only when a setting is missing. If the two drift apart, a missing
setting silently changes the model or the spending limits.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.chat.access import DEFAULT_QUESTIONS_PER_REVIEW
from backend.lambdas.ask_question import handler as ask_question
from backend.shared import admission, uploads

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "infra" / "modules" / "api-gateway"


def _variable_default(text: str, name: str) -> str:
    block = re.search(rf'variable "{name}" \{{(.*?)\n\}}', text, re.DOTALL)
    assert block, name
    value = re.search(r"^\s*default\s*=\s*(.+?)\s*$", block.group(1), re.MULTILINE)
    assert value, name
    return value.group(1).strip('"')


def test_chat_fallbacks_match_terraform_defaults():
    text = (API / "variables.tf").read_text()
    assert _variable_default(text, "chat_model_id") == ask_question.DEFAULT_MODEL_ID
    assert int(_variable_default(text, "chat_daily_budget_micro_usd")) == (
        ask_question.DEFAULT_DAILY_BUDGET_MICRO_USD
    )
    assert int(_variable_default(text, "chat_daily_max_questions")) == (
        ask_question.DEFAULT_DAILY_MAX_QUESTIONS
    )
    assert int(_variable_default(text, "chat_blocked_per_review")) == (
        ask_question.DEFAULT_BLOCKED_PER_REVIEW
    )
    assert int(_variable_default(text, "chat_questions_per_review")) == (
        DEFAULT_QUESTIONS_PER_REVIEW
    )


def test_paid_limit_fallbacks_match_terraform_defaults():
    text = (API / "admission.tf").read_text()
    block = re.search(
        r'variable "paid_limits" \{.*?default = \{(.*?)\n  \}', text, re.DOTALL
    )
    assert block
    limits = {
        key: int(value)
        for key, value in re.findall(r"(\w+)\s*=\s*(\d+)", block.group(1))
    }
    review = {"reviewId": "r1", "visitorKey": "v1", "ttl": 2**31}
    public = {
        key: (budget_default, count_default)
        for key, _budget, budget_default, _count, count_default, _ttl in (
            admission._public_scopes(review, "v1", "20260101", 0)
        )
    }
    assert public["paid#global#20260101"] == (
        limits["global_daily_budget"],
        limits["global_daily_requests"],
    )
    assert public["paid#visitor#v1#20260101"] == (
        limits["visitor_daily_budget"],
        limits["visitor_daily_requests"],
    )
    assert public["paid#review#r1"] == (
        limits["review_budget"],
        limits["review_requests"],
    )
    assert (
        limits["initial_reserve"],
        limits["clarify_reserve"],
        limits["deeper_reserve"],
    ) == (
        400_000,
        200_000,
        200_000,
    )


def test_upload_limit_fallbacks_match_terraform_defaults():
    text = (API / "admission.tf").read_text()
    block = re.search(
        r'variable "upload_limits" \{.*?default = \{(.*?)\n  \}', text, re.DOTALL
    )
    assert block
    limits = {
        key: int(value)
        for key, value in re.findall(r"(\w+)\s*=\s*(\d+)", block.group(1))
    }
    assert limits == {
        "global_daily": uploads.DEFAULT_UPLOADS_DAILY_MAX,
        "visitor_daily": uploads.DEFAULT_UPLOADS_VISITOR_DAILY_MAX,
    }
