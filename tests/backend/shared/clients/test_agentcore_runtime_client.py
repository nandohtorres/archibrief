import io
import json

from botocore.response import StreamingBody
from botocore.stub import Stubber

from backend.shared.clients import AgentCoreRuntimeClient


def _client() -> AgentCoreRuntimeClient:
    return AgentCoreRuntimeClient(
        agent_runtime_arn="arn:aws:bedrock-agentcore:us-east-1:000000000000:runtime/test",
        region_name="us-east-1",
    )


def test_invoke_sends_payload_and_parses_response():
    client = _client()
    stubber = Stubber(client._client)
    response_body = json.dumps({"status": "complete", "findings": []}).encode("utf-8")
    streaming_response = StreamingBody(io.BytesIO(response_body), len(response_body))
    stubber.add_response(
        "invoke_agent_runtime",
        {
            "response": streaming_response,
            "statusCode": 200,
            "contentType": "application/json",
        },
        {
            "agentRuntimeArn": client.agent_runtime_arn,
            "runtimeSessionId": "archibrief-deeper-session-review-r1-finding-f1",
            "payload": json.dumps({"mode": "deeper", "review_id": "r1"}).encode(
                "utf-8"
            ),
        },
    )
    stubber.activate()

    result = client.invoke(
        payload={"mode": "deeper", "review_id": "r1"},
        runtime_session_id="archibrief-deeper-session-review-r1-finding-f1",
    )

    stubber.assert_no_pending_responses()
    assert result == {"status": "complete", "findings": []}


def test_read_timeout_is_applied_and_invocations_are_never_retried():
    # botocore's default 60s read timeout and
    # automatic retries could outlive the API's 30s limit and start a
    # second paid run for the same request.
    client = AgentCoreRuntimeClient(
        agent_runtime_arn="arn:aws:bedrock-agentcore:us-east-1:000000000000:runtime/test",
        read_timeout_seconds=24,
    )
    config = client._client.meta.config
    assert config.read_timeout == 24
    assert config.retries["total_max_attempts"] == 1
