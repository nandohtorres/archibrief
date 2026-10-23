from decimal import Decimal
from types import SimpleNamespace

import pytest
from botocore.stub import Stubber

from backend.shared.clients import DynamoDBClient


def _client() -> DynamoDBClient:
    return DynamoDBClient(table_name="tbl", region_name="us-east-1")


def test_put_item_converts_floats_to_decimal_including_nested():
    client = _client()
    stubber = Stubber(client._table.meta.client)
    stubber.add_response(
        "put_item",
        {},
        {
            "TableName": "tbl",
            "Item": {
                "findingId": "f1",
                "confidence": Decimal("0.9"),
                "confidence_inputs": {
                    "evidence_directness": Decimal("0.5"),
                },
                "framework_mapping": [Decimal("1.5"), "SEC01"],
            },
        },
    )
    stubber.activate()

    client.put_item(
        {
            "findingId": "f1",
            "confidence": 0.9,
            "confidence_inputs": {"evidence_directness": 0.5},
            "framework_mapping": [1.5, "SEC01"],
        }
    )

    stubber.assert_no_pending_responses()


def test_query_all_follows_an_empty_filtered_page_without_mutating_the_request():
    client = DynamoDBClient.__new__(DynamoDBClient)
    calls = []
    pages = iter(
        [
            {"Items": [], "LastEvaluatedKey": {"reviewId": "r", "findingId": "first"}},
            {"Items": [{"findingId": "child"}]},
        ]
    )

    def query(**kwargs):
        calls.append(kwargs)
        return next(pages)

    client._table = SimpleNamespace(query=query)
    assert client.query_all(
        KeyConditionExpression="reviewId = :rid", ConsistentRead=True
    ) == [{"findingId": "child"}]
    assert "ExclusiveStartKey" not in calls[0]
    assert calls[1]["ExclusiveStartKey"]["findingId"] == "first"
    assert all(call["ConsistentRead"] for call in calls)


def test_query_all_fails_instead_of_silently_truncating_a_report():
    client = DynamoDBClient.__new__(DynamoDBClient)
    client._table = SimpleNamespace(
        query=lambda **kwargs: {
            "Items": [{"findingId": "child"}],
            "LastEvaluatedKey": {"findingId": "next"},
        }
    )
    with pytest.raises(ValueError, match="pagination limit"):
        client.query_all(max_pages=2)
