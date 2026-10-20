from botocore.stub import Stubber

from backend.shared.clients import S3VectorsClient


def _client() -> S3VectorsClient:
    return S3VectorsClient(bucket_name="bkt", index_name="idx", region_name="us-east-1")


def test_list_vectors_returns_single_page():
    client = _client()
    stubber = Stubber(client._client)
    stubber.add_response(
        "list_vectors",
        {"vectors": [{"key": "c-0000", "metadata": {"content_hash": "h0"}}]},
        {"vectorBucketName": "bkt", "indexName": "idx", "returnMetadata": True},
    )
    stubber.activate()

    result = client.list_vectors()

    stubber.assert_no_pending_responses()
    assert result == [{"key": "c-0000", "metadata": {"content_hash": "h0"}}]


def test_list_vectors_paginates_until_next_token_is_absent():
    client = _client()
    stubber = Stubber(client._client)
    stubber.add_response(
        "list_vectors",
        {"vectors": [{"key": "c-0000"}], "nextToken": "page-2"},
        {"vectorBucketName": "bkt", "indexName": "idx", "returnMetadata": True},
    )
    stubber.add_response(
        "list_vectors",
        {"vectors": [{"key": "c-0001"}]},
        {
            "vectorBucketName": "bkt",
            "indexName": "idx",
            "returnMetadata": True,
            "nextToken": "page-2",
        },
    )
    stubber.activate()

    result = client.list_vectors()

    stubber.assert_no_pending_responses()
    assert [v["key"] for v in result] == ["c-0000", "c-0001"]


def test_list_vectors_returns_empty_list_when_index_is_empty():
    client = _client()
    stubber = Stubber(client._client)
    stubber.add_response(
        "list_vectors",
        {"vectors": []},
        {"vectorBucketName": "bkt", "indexName": "idx", "returnMetadata": True},
    )
    stubber.activate()

    result = client.list_vectors()

    stubber.assert_no_pending_responses()
    assert result == []


def test_delete_vectors_sends_keys():
    client = _client()
    stubber = Stubber(client._client)
    stubber.add_response(
        "delete_vectors",
        {},
        {"vectorBucketName": "bkt", "indexName": "idx", "keys": ["c-0000", "c-0001"]},
    )
    stubber.activate()

    client.delete_vectors(["c-0000", "c-0001"])

    stubber.assert_no_pending_responses()
