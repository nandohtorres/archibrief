from decimal import Decimal

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
