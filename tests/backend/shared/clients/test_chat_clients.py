"""Client methods the chat uses (ADR-0050): cached forced-tool Converse,
Guardrails verdicts and grounding scores, and DynamoDB transactions."""

from __future__ import annotations

import boto3
import pytest
from botocore.stub import ANY, Stubber
from moto import mock_aws

from backend.shared.clients import (
    BedrockReasoningClient,
    DynamoDBTransactionClient,
    GuardrailsClient,
    ModelOutputTruncated,
    ToolCallMissing,
    TransactionCanceled,
)

_SCHEMA = {"type": "object", "properties": {"status": {"type": "string"}}}


def _converse_response(
    content: list[dict], stop_reason: str = "tool_use", usage=None
) -> dict:
    return {
        "output": {"message": {"role": "assistant", "content": content}},
        "stopReason": stop_reason,
        "usage": usage or {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
        "metrics": {"latencyMs": 100},
    }


def _call(client: BedrockReasoningClient):
    return client.converse_tool_cached(
        system_prompt="system",
        cached_user_text="review block",
        user_text="question block",
        max_tokens=700,
        tool_name="answer_question",
        tool_description="answer",
        input_schema=_SCHEMA,
    )


def test_cached_call_places_cache_points_and_returns_usage():
    client = BedrockReasoningClient(model_id="m")
    stubber = Stubber(client._client)
    stubber.add_response(
        "converse",
        _converse_response(
            [
                {
                    "toolUse": {
                        "toolUseId": "t1",
                        "name": "answer_question",
                        "input": {"status": "ok"},
                    }
                }
            ],
            usage={
                "inputTokens": 100,
                "outputTokens": 40,
                "totalTokens": 140,
                "cacheReadInputTokens": 900,
                "cacheWriteInputTokens": 0,
            },
        ),
        {
            "modelId": "m",
            "system": [{"text": "system"}, {"cachePoint": {"type": "default"}}],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"text": "review block"},
                        {"cachePoint": {"type": "default"}},
                        {"text": "question block"},
                    ],
                }
            ],
            "inferenceConfig": {"maxTokens": 700, "temperature": 0},
            "toolConfig": ANY,
        },
    )
    with stubber:
        result, usage = _call(client)
    assert result == {"status": "ok"}
    assert usage == {
        "inputTokens": 100,
        "outputTokens": 40,
        "cacheReadInputTokens": 900,
        "cacheWriteInputTokens": 0,
    }


def test_cached_call_fails_closed_on_truncation_and_missing_tool():
    client = BedrockReasoningClient(model_id="m")
    stubber = Stubber(client._client)
    stubber.add_response(
        "converse", _converse_response([{"text": "x"}], stop_reason="max_tokens")
    )
    stubber.add_response("converse", _converse_response([{"text": "plain answer"}]))
    with stubber:
        with pytest.raises(ModelOutputTruncated):
            _call(client)
        with pytest.raises(ToolCallMissing):
            _call(client)


def test_chat_client_has_a_read_timeout_and_never_retries():
    client = BedrockReasoningClient(
        model_id="m", read_timeout_seconds=20, no_retries=True
    )
    config = client._client.meta.config
    assert config.read_timeout == 20
    assert config.retries["total_max_attempts"] == 1


def test_review_client_keeps_botocore_defaults():
    config = BedrockReasoningClient(model_id="m")._client.meta.config
    assert config.read_timeout == 60


def _guardrail_response(action: str, assessments: list[dict]) -> dict:
    usage = {
        key: 0
        for key in (
            "topicPolicyUnits",
            "contentPolicyUnits",
            "wordPolicyUnits",
            "sensitiveInformationPolicyUnits",
            "sensitiveInformationPolicyFreeUnits",
            "contextualGroundingPolicyUnits",
        )
    }
    return {"usage": usage, "action": action, "outputs": [], "assessments": assessments}


def test_assess_names_the_filters_that_fired():
    client = GuardrailsClient(guardrail_id="g", guardrail_version="1")
    stubber = Stubber(client._client)
    stubber.add_response(
        "apply_guardrail",
        _guardrail_response(
            "GUARDRAIL_INTERVENED",
            [
                {
                    "contentPolicy": {
                        "filters": [
                            {
                                "type": "PROMPT_ATTACK",
                                "confidence": "HIGH",
                                "action": "BLOCKED",
                            }
                        ]
                    },
                    "topicPolicy": {
                        "topics": [
                            {
                                "name": "OtherUsersData",
                                "type": "DENY",
                                "action": "BLOCKED",
                            }
                        ]
                    },
                }
            ],
        ),
        {
            "guardrailIdentifier": "g",
            "guardrailVersion": "1",
            "source": "INPUT",
            "content": [{"text": {"text": "question"}}],
        },
    )
    stubber.add_response("apply_guardrail", _guardrail_response("NONE", []))
    with stubber:
        blocked = client.assess("question")
        allowed = client.assess("question")
    assert blocked.blocked is True
    assert blocked.filters == ["PROMPT_ATTACK", "topic:OtherUsersData"]
    assert allowed.blocked is False
    assert allowed.filters == []


def test_grounding_scores_send_qualifiers_and_read_scores():
    client = GuardrailsClient(guardrail_id="g", guardrail_version="1")
    stubber = Stubber(client._client)
    stubber.add_response(
        "apply_guardrail",
        _guardrail_response(
            "NONE",
            [
                {
                    "contextualGroundingPolicy": {
                        "filters": [
                            {
                                "type": "GROUNDING",
                                "threshold": 0.0,
                                "score": 0.82,
                                "action": "NONE",
                            },
                            {
                                "type": "RELEVANCE",
                                "threshold": 0.0,
                                "score": 0.9,
                                "action": "NONE",
                            },
                        ]
                    }
                }
            ],
        ),
        {
            "guardrailIdentifier": "g",
            "guardrailVersion": "1",
            "source": "OUTPUT",
            "content": [
                {"text": {"text": "source", "qualifiers": ["grounding_source"]}},
                {"text": {"text": "query", "qualifiers": ["query"]}},
                {"text": {"text": "answer", "qualifiers": ["guard_content"]}},
            ],
        },
    )
    with stubber:
        scores = client.grounding_scores("source", "query", "answer")
    assert scores == {"GROUNDING": 0.82, "RELEVANCE": 0.9}


@mock_aws
def test_transaction_writes_all_or_nothing_and_reports_which_condition_failed():
    ddb = boto3.client("dynamodb", region_name="us-east-1")
    ddb.create_table(
        TableName="t",
        KeySchema=[{"AttributeName": "k", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "k", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    client = DynamoDBTransactionClient()
    increment = {
        "Update": {
            "TableName": "t",
            "Key": {"k": "counter"},
            "UpdateExpression": "SET n = if_not_exists(n, :zero) + :one",
            "ConditionExpression": "attribute_not_exists(n) OR n < :max",
            "ExpressionAttributeValues": {":zero": 0, ":one": 1, ":max": 1},
        }
    }
    client.transact_write(
        [increment, {"Put": {"TableName": "t", "Item": {"k": "q1", "score": 0.5}}}]
    )
    table = boto3.resource("dynamodb", region_name="us-east-1").Table("t")
    assert table.get_item(Key={"k": "counter"})["Item"]["n"] == 1

    with pytest.raises(TransactionCanceled) as exc:
        client.transact_write(
            [{"Put": {"TableName": "t", "Item": {"k": "q2"}}}, increment]
        )
    assert exc.value.reasons[1] == "ConditionalCheckFailed"
    assert exc.value.reasons[0] in ("None", "")
    # Nothing from the cancelled transaction was written.
    assert "Item" not in table.get_item(Key={"k": "q2"})
