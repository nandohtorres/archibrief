"""GET /reviews/{reviewId}/questions (ADR-0050): the transcript, the
suggested questions and the remaining count. No model, no cost."""

from __future__ import annotations

import json
import time
import uuid

from backend.lambdas.list_questions.handler import handler as list_handler
from tests.backend import visitor
from tests.backend.lambdas.ask_question.test_handler import _ask, _call, _event


def _list(review_id="r1"):
    response = list_handler(_event(None, review_id=review_id, raw=""), None)
    return response["statusCode"], json.loads(response["body"])


def test_expired_review_hides_the_transcript(env):
    _call(_ask())
    env.reviews.update_item(
        Key={"reviewId": "r1"},
        UpdateExpression="SET #t = :t",
        ExpressionAttributeNames={"#t": "ttl"},
        ExpressionAttributeValues={":t": 1},
    )
    assert _list()[0] == 404


def test_lists_the_conversation_in_order_with_suggestions(env):
    _call(_ask("First?"))
    _call(_ask("Second?"))
    _call({"client_request_id": str(uuid.uuid4()), "suggested_id": "s1"})
    status, body = _list()
    assert status == 200
    assert [q["question"] for q in body["questions"]] == [
        "First?",
        "Second?",
        "Which issues should I fix first, and why?",
    ]
    assert body["questions"][0]["status"] == "answered"
    assert body["questions"][0]["answer"][0]["citations"][0]["kind"] == "finding"
    suggested = {s["id"]: s["answered"] for s in body["suggested"]}
    assert suggested["s1"] is True and suggested["s2"] is False
    assert body["questions_remaining"] == 3
    assert body["limit"] == 5


def test_expired_failed_and_in_flight_questions_are_left_out(env):
    now = int(time.time())
    for key, status, ttl in [
        ("Q#old", "answered", now - 10),
        ("Q#failed", "failed", now + 100),
        ("Q#busy", "in_flight", now + 100),
    ]:
        env.questions.put_item(
            Item={
                "reviewId": "r1",
                "questionKey": key,
                "status": status,
                "ttl": ttl,
                "createdAt": now,
                "question": key,
            }
        )
    status, body = _list()
    assert status == 200
    assert body["questions"] == []


def test_access_and_missing_reviews(env, monkeypatch):
    monkeypatch.setenv("CHAT_PUBLIC_ENABLED", "false")
    assert _list() == (403, {"error": "chat_not_public"})
    monkeypatch.setenv("CHAT_PUBLIC_ENABLED", "true")
    assert _list(review_id="nope")[0] == 404
    env.reviews.put_item(
        Item={
            "reviewId": "r2",
            "status": "pending",
            "ttl": int(time.time()) + 86400,
            **visitor.review_fields(),
        }
    )
    assert _list(review_id="r2")[0] == 409
    status, body = _list()
    assert status == 200 and body["limit"] == 5


def test_listing_never_calls_the_model(env):
    _list()
    assert env.reasoning.calls == []


def test_listing_fails_closed_on_missing_or_malformed_expiry(env):
    for key, expiry in [("Q#missing", None), ("Q#malformed", "invalid")]:
        item = {
            "reviewId": "r1",
            "questionKey": key,
            "status": "answered",
            "createdAt": 1,
            "question": "Private expired text",
        }
        if expiry is not None:
            item["ttl"] = expiry
        env.questions.put_item(Item=item)
    status, body = _list()
    assert status == 200
    assert body["questions"] == []
