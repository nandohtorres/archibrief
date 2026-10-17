"""ArchiBrief Lambda: ask_question.

POST /reviews/{reviewId}/questions — one grounded question about one
finished review (ADR-0046 §4, ADR-0050). Synchronous: the API integration
allows 29 s, this Lambda 28 s, the model call up to 24 s with no retry.

Request body (unknown fields are rejected, which is how a forged
`history` is refused; history is always loaded server-side):

    {"client_request_id": "<uuid4>", "question": "...",
     "focus_finding_id": "<finding uuid>" | null,
     "suggested_id": "s2" | null}

`question` is required unless `suggested_id` is set, in which case the
suggestion's own text is asked.

Order of checks, cheapest and most decisive first:
1. Who may ask: admin key, or CHAT_PUBLIC_ENABLED (off until the chat
   opens to the public).
2. Body shape, then the kill switch (fails closed; the admin key doesn't
   bypass it).
3. The review exists and is complete.
4. Idempotency: a repeated client_request_id returns the stored answer.
5. Suggested question already answered → served free (and a repeat
   click returns the transcript's existing record instead of a copy).
6. Stages 1–2 (normalize, bound), then atomically claim the question and
   reserve screening cost and a daily request before stage 3 (Guardrails).
   A blocked question costs screening but uses no review question slot.
7. Atomic model admission: the review's question slot (custom questions
   only; the admin key isn't limited), the owned screening claim and the
   remaining worst-case cost reservation. Suggestions skip screening and
   reserve their whole cost and daily count in this transaction.
8. The paid call (backend/chat/answer.py), then settle the reservation to
   the estimated real cost. A failed call refunds the review's slot; the
   reservation stays spent, since Bedrock may have billed.

Every AWS call on the paid path is bounded (connect + read timeout, no
retries) and the model's read timeout is sized, after retrieval, to the
time the Lambda has left, so a slow dependency becomes a 504 with a
refund rather than the Lambda being killed with the question stuck in
flight.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from botocore.exceptions import ClientError, ConnectTimeoutError, ReadTimeoutError

from backend.chat.access import (
    FINAL_STATUSES,
    caller_allowed,
    is_admin,
    question_is_live,
    questions_per_review,
    transcript_item,
)
from backend.chat.answer import MODEL_CONNECT_TIMEOUT_SECONDS, ChatClients, answer_question
from backend.chat.context import ReviewContext, build_review_context
from backend.chat.observe import log_chat_event, question_hash
from backend.chat.pricing import GUARDRAIL_INPUT_MICRO_USD_PER_UNIT, reserve_micro_usd
from backend.chat.prompt import MAX_OUTPUT_TOKENS, PROMPT_VERSION, build_system_prompt
from backend.chat.suggested import find_suggestion
from backend.chat.verify import REFUSAL_TEXTS, MalformedAnswer, VerifiedAnswer
from backend.shared.clients import (
    BedrockEmbeddingClient,
    BedrockReasoningClient,
    DynamoDBClient,
    DynamoDBTransactionClient,
    GuardrailsClient,
    ModelOutputTruncated,
    S3Client,
    S3VectorsClient,
    ToolCallMissing,
    TransactionCanceled,
    UnexpectedStopReason,
)
from backend.shared.kill_switch import paid_work_allowed
from backend.shared.sanitize import QuestionRejected, check_question

# The small calls (Guardrails, embedding, S3 Vectors) normally take well
# under a second.
SMALL_CALL_READ_TIMEOUT_SECONDS = 2
SMALL_CALL_CONNECT_TIMEOUT_SECONDS = 1
LAMBDA_TIMEOUT_SECONDS = 28
# Time kept back at the end to mark a failed question and refund it.
DEADLINE_MARGIN_SECONDS = 1.5
# Same reasoning as deeper_review: longer than the Lambda timeout, so a run
# that timed out still blocks an immediate duplicate.
IN_FLIGHT_STALE_SECONDS = 90
QUESTION_TTL_SECONDS = 7 * 24 * 3600
COUNTER_TTL_SECONDS = 48 * 3600
MAX_BODY_BYTES = 4096
DEFAULT_BLOCKED_PER_REVIEW = 5
DEFAULT_DAILY_BUDGET_MICRO_USD = 1_000_000  # $1/day, matches API module defaults
DEFAULT_MODEL_ID = "us.anthropic.claude-sonnet-4-6"
DEFAULT_DAILY_MAX_QUESTIONS = 100
# Failed paid calls per review: the first few give the question back, and
# after MAX_FAILURES_PER_REVIEW the review stops accepting paid questions.
MAX_REFUNDED_FAILURES = 3
RETRYABLE_BEDROCK_ERRORS = {
    "ThrottlingException",
    "ServiceUnavailableException",
    "ModelNotReadyException",
    "InternalServerException",
    "ModelTimeoutException",
}
MAX_FAILURES_PER_REVIEW = 6
_ALLOWED_FIELDS = {"client_request_id", "question", "focus_finding_id", "suggested_id"}
_REVIEW_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SUGGESTED_ID = re.compile(r"^s\d{1,2}$")

ERROR_MESSAGES = {
    "invalid_request": "That request couldn't be read.",
    "invalid_question": "Please ask in plain text, in under 500 characters.",
    "chat_not_public": "Questions are open to the site owner only for now.",
    "review_not_found": "That review doesn't exist or has expired.",
    "review_not_complete": "Questions open once the review is finished.",
    "request_in_progress": "That question is still being answered. Try again in a moment.",
    "request_expired": "That saved answer has expired. Start a new question.",
    "review_quota_exhausted": "You've used this review's questions.",
    "daily_cap_reached": "Today's free questions are used up. Try again tomorrow.",
    "too_many_blocked": "Too many questions on this review couldn't be processed.",
    "too_many_failed": "Answers on this review keep failing. Try again later.",
    "answer_failed": "The answer couldn't be completed. Your question wasn't counted.",
    "answer_timeout": "The answer took too long. Your question wasn't counted.",
    "chat_paused": "Chat is paused right now.",
    "guardrails_unavailable": "Questions can't be checked right now. Try again shortly.",
    "chat_busy": "Lots of questions at once. Try again in a moment.",
}


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def _error(status_code: int, code: str) -> dict[str, Any]:
    return _response(status_code, {"error": code, "message": ERROR_MESSAGES[code]})


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _parse_body(event: dict) -> dict[str, Any] | None:
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None
    if len(raw.encode("utf-8")) > MAX_BODY_BYTES:
        return None
    try:
        body = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(body, dict) or set(body) - _ALLOWED_FIELDS:
        return None
    try:
        request_id = uuid.UUID(str(body.get("client_request_id")))
    except ValueError:
        return None
    if request_id.version != 4:
        return None
    body["client_request_id"] = str(request_id)
    suggested = body.get("suggested_id")
    if suggested is not None and not (
        isinstance(suggested, str) and _SUGGESTED_ID.fullmatch(suggested)
    ):
        return None
    focus = body.get("focus_finding_id")
    if focus is not None and not isinstance(focus, str):
        return None
    return body


def _day(now: float) -> str:
    return datetime.fromtimestamp(now, UTC).strftime("%Y%m%d")


class _Tables:
    def __init__(self) -> None:
        self.reviews_name = os.environ["REVIEWS_TABLE_NAME"]
        self.questions_name = os.environ["QUESTIONS_TABLE_NAME"]
        self.counters_name = os.environ["USAGE_COUNTERS_TABLE_NAME"]
        self.reviews = DynamoDBClient(table_name=self.reviews_name)
        self.questions = DynamoDBClient(table_name=self.questions_name)
        self.counters = DynamoDBClient(table_name=self.counters_name)
        self.transactions = DynamoDBTransactionClient()


_SMALL_CALL: dict[str, Any] = {
    "read_timeout_seconds": SMALL_CALL_READ_TIMEOUT_SECONDS,
    "connect_timeout_seconds": SMALL_CALL_CONNECT_TIMEOUT_SECONDS,
    "no_retries": True,
}


def _deadline(context: object, started: float) -> float:
    """The time.monotonic() value this request has to finish by."""
    try:
        remaining = context.get_remaining_time_in_millis() / 1000  # type: ignore[attr-defined]
    except AttributeError:
        remaining = LAMBDA_TIMEOUT_SECONDS
    return started + remaining - DEADLINE_MARGIN_SECONDS


def _vectors_client() -> S3VectorsClient | None:
    """None when the client can't be built (for example a Lambda runtime
    boto3 too old to know s3vectors). Retrieval then fails open: the
    model can still cite the review itself."""
    try:
        return S3VectorsClient(
            bucket_name=os.environ["VECTOR_BUCKET_NAME"],
            index_name=os.environ["VECTOR_INDEX_NAME"],
            **_SMALL_CALL,
        )
    except Exception:  # noqa: BLE001 - fail open, see docstring
        log_chat_event(event="chat_retrieval_unavailable", outcome="failed_open")
        return None


def _clients(model_id: str) -> ChatClients:
    grounding_id = os.environ.get("CHAT_GROUNDING_GUARDRAIL_ID", "")
    return ChatClients(
        # Built after retrieval, with the read timeout the time left allows
        # (answer.model_read_timeout).
        make_reasoning=lambda read_timeout: BedrockReasoningClient(
            model_id=model_id,
            read_timeout_seconds=read_timeout,
            connect_timeout_seconds=MODEL_CONNECT_TIMEOUT_SECONDS,
            no_retries=True,
        ),
        embedding=BedrockEmbeddingClient(**_SMALL_CALL),
        vectors=_vectors_client(),
        grounding=(
            GuardrailsClient(
                guardrail_id=grounding_id,
                guardrail_version=os.environ.get("CHAT_GROUNDING_GUARDRAIL_VERSION", "1"),
                **_SMALL_CALL,
            )
            if grounding_id
            else None
        ),
    )


def _history(tables: _Tables, review_id: str, exclude_key: str, now: float) -> list[dict]:
    items = tables.questions.query(
        KeyConditionExpression="reviewId = :r AND begins_with(questionKey, :q)",
        ExpressionAttributeValues={":r": review_id, ":q": "Q#"},
    )
    turns = [
        i
        for i in items
        if i["questionKey"] != exclude_key
        # Only answered turns. A refused question, and above all one
        # Guardrails blocked, must not reach the model as history on a
        # later turn.
        and i.get("status") in ("answered", "not_determinable")
        and question_is_live(i, now)
    ]
    turns.sort(key=lambda i: (int(i.get("createdAt", 0)), str(i.get("askedAt", ""))))
    return turns


def _asked_suggestion(
    tables: _Tables, review_id: str, suggested_id: str, now: float
) -> dict[str, Any] | None:
    """The transcript's existing record for this suggestion, if it was
    already asked on this review. A repeat click returns it instead of
    adding a duplicate to the transcript."""
    items = tables.questions.query(
        KeyConditionExpression="reviewId = :r AND begins_with(questionKey, :q)",
        ExpressionAttributeValues={":r": review_id, ":q": "Q#"},
    )
    asked = [
        i
        for i in items
        if i.get("suggestedId") == suggested_id
        and i.get("status") in FINAL_STATUSES
        and question_is_live(i, now)
    ]
    return min(asked, key=lambda i: int(i.get("createdAt", 0))) if asked else None


def _remaining(review_item: dict[str, Any], limit: int) -> int:
    return max(0, limit - int(review_item.get("questionsUsed", 0)))


def _success(item: dict[str, Any], remaining: int, limit: int, admin: bool) -> dict[str, Any]:
    return _response(
        200,
        {
            **transcript_item(item),
            "questions_remaining": remaining,
            "limit": limit,
            "limit_applies": not admin,
        },
    )


def _record_blocked(tables: _Tables, review_id: str, admin: bool, max_blocked: int) -> bool:
    """+1 on the review's blocked counter; False once over the limit."""
    kwargs: dict[str, Any] = {
        "Key": {"reviewId": review_id},
        "UpdateExpression": "SET chatBlocked = if_not_exists(chatBlocked, :zero) + :one",
        "ExpressionAttributeValues": {":zero": 0, ":one": 1},
    }
    if not admin:
        kwargs["ConditionExpression"] = "attribute_not_exists(chatBlocked) OR chatBlocked < :max"
        kwargs["ExpressionAttributeValues"][":max"] = max_blocked
    try:
        tables.reviews.update_item(**kwargs)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def _record_failure(tables: _Tables, review_id: str, refund: bool) -> None:
    """Count a failed paid call on the review, and give the question back
    for the first MAX_REFUNDED_FAILURES of them. Without the cap, failed
    calls (refunded, but billed) would be bounded only by the daily cap."""
    if refund:
        try:
            tables.reviews.update_item(
                Key={"reviewId": review_id},
                UpdateExpression="SET chatFailed = if_not_exists(chatFailed, :zero) + :one "
                "ADD questionsUsed :minus",
                ConditionExpression="questionsUsed > :zero AND "
                "(attribute_not_exists(chatFailed) OR chatFailed < :max)",
                ExpressionAttributeValues={
                    ":minus": -1,
                    ":zero": 0,
                    ":one": 1,
                    ":max": MAX_REFUNDED_FAILURES,
                },
            )
            return
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
    tables.reviews.update_item(
        Key={"reviewId": review_id},
        UpdateExpression="SET chatFailed = if_not_exists(chatFailed, :zero) + :one",
        ExpressionAttributeValues={":zero": 0, ":one": 1},
    )


# The day's chat spend counter. It counts what's been spent (reservations,
# settled to the estimated real cost) and is compared with the budget in
# force on every question, so a budget change applies at once rather than
# on the next UTC day.
def _spend_key(day: str) -> dict[str, str]:
    return {"counterKey": f"global#{day}#chat_spent_micro_usd"}


def _precheck(
    tables: _Tables,
    review: dict[str, Any],
    admin: bool,
    counts_slot: bool,
    reserve: int,
    now: float,
) -> str | None:
    """Cheap reads before any spend, so a review or day that's used up
    doesn't keep paying for Guardrails checks. The admission transaction
    still decides; this only
    turns away requests that would certainly fail it."""
    if not admin:
        if counts_slot and int(review.get("questionsUsed", 0)) >= questions_per_review():
            return "review_quota_exhausted"
        if int(review.get("chatFailed", 0)) >= MAX_FAILURES_PER_REVIEW:
            return "too_many_failed"
        if counts_slot and int(review.get("chatBlocked", 0)) >= _env_int(
            "CHAT_BLOCKED_PER_REVIEW", DEFAULT_BLOCKED_PER_REVIEW
        ):
            return "too_many_blocked"
    day = _day(now)
    budget = _env_int("CHAT_DAILY_BUDGET_MICRO_USD", DEFAULT_DAILY_BUDGET_MICRO_USD)
    spent = tables.counters.get_item(_spend_key(day))
    if int((spent or {}).get("spent", 0)) + reserve > budget:
        return "daily_cap_reached"
    count = tables.counters.get_item({"counterKey": f"global#{day}#chat_questions"})
    max_count = _env_int("CHAT_DAILY_MAX_QUESTIONS", DEFAULT_DAILY_MAX_QUESTIONS)
    if count is not None and int(count.get("n", 0)) >= max_count:
        return "daily_cap_reached"
    return None


def _mark_failed(
    tables: _Tables, review_id: str, keys: list[str], error: str, claim: str | None = None
) -> None:
    for key in keys:
        update: dict[str, Any] = {
            "Key": {"reviewId": review_id, "questionKey": key},
            "UpdateExpression": "SET #s = :failed, errorCode = :e",
            "ExpressionAttributeNames": {"#s": "status"},
            "ExpressionAttributeValues": {":failed": "failed", ":e": error},
        }
        if claim:
            update["ConditionExpression"] = "#s = :screening AND screeningClaim = :claim"
            update["ExpressionAttributeValues"].update({":screening": "screening", ":claim": claim})
        try:
            tables.questions.update_item(**update)
        except ClientError as exc:
            if not claim or exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise


def _admit(
    tables: _Tables,
    review_id: str,
    question_item: dict[str, Any],
    suggestion_key: str | None,
    count_slot: bool,
    admin: bool,
    reserve: int,
    now: float,
) -> str | None:
    """The admission transaction. None on success, else an error code."""
    limit = questions_per_review()
    budget = _env_int("CHAT_DAILY_BUDGET_MICRO_USD", DEFAULT_DAILY_BUDGET_MICRO_USD)
    max_count = _env_int("CHAT_DAILY_MAX_QUESTIONS", DEFAULT_DAILY_MAX_QUESTIONS)
    if reserve > budget or max_count <= 0:
        return "daily_cap_reached"
    day = _day(now)
    counter_ttl = int(now) + COUNTER_TTL_SECONDS
    record_condition = "attribute_not_exists(questionKey) OR attribute_not_exists(#expiry) OR #s = :failed OR #expiry <= :now OR ((#s = :in_flight OR #s = :screening) AND createdAt < :stale)"
    record_values = {
        ":failed": "failed",
        ":in_flight": "in_flight",
        ":screening": "screening",
        ":stale": int(now) - IN_FLIGHT_STALE_SECONDS,
        ":now": int(now),
    }
    screened = bool(question_item.get("screeningClaim")) and question_item["status"] != "screening"
    record_names = {"#s": "status", "#expiry": "ttl"}
    if screened:
        record_condition = "#s = :screening AND #claim = :claim"
        record_names = {"#s": "status", "#claim": "screeningClaim"}
        record_values = {":screening": "screening", ":claim": question_item["screeningClaim"]}
    actions: list[dict[str, Any]] = []
    roles: list[str] = []
    if count_slot:
        update: dict[str, Any] = {
            "TableName": tables.reviews_name,
            "Key": {"reviewId": review_id},
            "UpdateExpression": "SET questionsUsed = if_not_exists(questionsUsed, :zero) + :one",
            "ExpressionAttributeValues": {":zero": 0, ":one": 1},
        }
        if not admin:
            update["ConditionExpression"] = (
                "attribute_not_exists(questionsUsed) OR questionsUsed < :max"
            )
            update["ExpressionAttributeValues"][":max"] = limit
        actions.append({"Update": update})
        roles.append("review_slot")
    actions.append(
        {
            "Put": {
                "TableName": tables.questions_name,
                "Item": question_item,
                "ConditionExpression": record_condition,
                "ExpressionAttributeNames": record_names,
                "ExpressionAttributeValues": record_values,
            }
        }
    )
    roles.append("question_record")
    if suggestion_key:
        actions.append(
            {
                "Put": {
                    "TableName": tables.questions_name,
                    "Item": {
                        "reviewId": review_id,
                        "questionKey": suggestion_key,
                        "status": "in_flight",
                        "createdAt": int(now),
                        "ttl": question_item["ttl"],
                    },
                    "ConditionExpression": record_condition,
                    "ExpressionAttributeNames": {"#s": "status", "#expiry": "ttl"},
                    "ExpressionAttributeValues": record_values,
                }
            }
        )
        roles.append("suggestion_record")
    actions.append(
        {
            "Update": {
                "TableName": tables.counters_name,
                "Key": _spend_key(day),
                "UpdateExpression": "SET spent = if_not_exists(spent, :zero) + :reserve, "
                "#ttl = if_not_exists(#ttl, :ttl)",
                # spent + reserve <= budget, written so DynamoDB can check it.
                "ConditionExpression": "attribute_not_exists(spent) OR spent <= :room",
                "ExpressionAttributeNames": {"#ttl": "ttl"},
                "ExpressionAttributeValues": {
                    ":zero": 0,
                    ":reserve": reserve,
                    ":room": budget - reserve,
                    ":ttl": counter_ttl,
                },
            }
        }
    )
    roles.append("daily_budget")
    # Typed questions already counted when their screening claim was made.
    if not screened:
        actions.append(
            {
                "Update": {
                    "TableName": tables.counters_name,
                    "Key": {"counterKey": f"global#{day}#chat_questions"},
                    "UpdateExpression": "SET n = if_not_exists(n, :zero) + :one, "
                    "#ttl = if_not_exists(#ttl, :ttl)",
                    "ConditionExpression": "attribute_not_exists(n) OR n < :max",
                    "ExpressionAttributeNames": {"#ttl": "ttl"},
                    "ExpressionAttributeValues": {
                        ":zero": 0,
                        ":one": 1,
                        ":max": max_count,
                        ":ttl": counter_ttl,
                    },
                }
            }
        )
        roles.append("daily_count")
    try:
        tables.transactions.transact_write(actions)
    except TransactionCanceled as exc:
        # Only a failed condition means a limit was hit. Anything else
        # (TransactionConflict on the shared daily counters when two
        # questions land at once, throttling) is a retryable collision,
        # not "today's questions are used up".
        failed = {
            roles[i]
            for i, reason in enumerate(exc.reasons[: len(roles)])
            if reason == "ConditionalCheckFailed"
        }
        if "question_record" in failed or "suggestion_record" in failed:
            return "request_in_progress"
        if "review_slot" in failed:
            return "review_quota_exhausted"
        if failed & {"daily_budget", "daily_count"}:
            return "daily_cap_reached"
        return "chat_busy"
    return None


def _settle(tables: _Tables, reserve: int, actual: int, now: float) -> None:
    tables.counters.update_item(
        Key=_spend_key(_day(now)),
        UpdateExpression="ADD spent :delta",
        ExpressionAttributeValues={":delta": actual - reserve},
    )


def _answer_fields(answer: VerifiedAnswer) -> dict[str, Any]:
    return {
        "status": answer.status,
        "refusalReason": answer.refusal_reason,
        "answer": answer.paragraphs,
    }


def handler(event: dict, context: object) -> dict:
    started = time.monotonic()
    deadline = _deadline(context, started)
    now = time.time()
    admin = is_admin(event)
    review_id = (event.get("pathParameters") or {}).get("reviewId", "")
    log: dict[str, Any] = {"review_id": review_id, "admin": admin}

    def finish(response: dict[str, Any], outcome: str, **fields: Any) -> dict[str, Any]:
        log_chat_event(
            **log,
            **fields,
            outcome=outcome,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        return response

    if not caller_allowed(admin):
        return finish(_error(403, "chat_not_public"), "rejected", error="chat_not_public")
    if not isinstance(review_id, str) or not _REVIEW_ID.fullmatch(review_id):
        return finish(_error(400, "invalid_request"), "rejected", error="invalid_request")
    body = _parse_body(event)
    if body is None:
        return finish(_error(400, "invalid_request"), "rejected", error="invalid_request")
    log["request_id"] = body["client_request_id"]
    if not paid_work_allowed():
        return finish(_error(503, "chat_paused"), "rejected", error="chat_paused")

    tables = _Tables()
    review = tables.reviews.get_item({"reviewId": review_id})
    if review is None:
        return finish(_error(404, "review_not_found"), "rejected", error="review_not_found")
    if review.get("status") != "complete" or not review.get("reportS3Key"):
        return finish(_error(409, "review_not_complete"), "rejected", error="review_not_complete")
    limit = questions_per_review()

    question_key = f"Q#{body['client_request_id']}"
    existing = tables.questions.get_item({"reviewId": review_id, "questionKey": question_key})
    if (
        existing
        and existing.get("status") in FINAL_STATUSES
        and not question_is_live(existing, now)
    ):
        return finish(_error(410, "request_expired"), "rejected", error="request_expired")
    if existing and existing.get("status") in FINAL_STATUSES:
        return finish(_success(existing, _remaining(review, limit), limit, admin), "replayed")
    if (
        existing
        and existing.get("status") == "in_flight"
        and int(existing.get("createdAt", 0)) >= int(now) - IN_FLIGHT_STALE_SECONDS
    ):
        return finish(_error(409, "request_in_progress"), "rejected", error="request_in_progress")

    ledger = json.loads(
        S3Client(bucket=os.environ["REPORTS_BUCKET_NAME"]).get_object(review["reportS3Key"])
    )
    ctx: ReviewContext = build_review_context(ledger)
    asked_at = datetime.fromtimestamp(now, UTC).isoformat()
    base_item: dict[str, Any] = {
        "reviewId": review_id,
        "questionKey": question_key,
        "createdAt": int(now),
        "askedAt": asked_at,
        "ttl": int(now) + QUESTION_TTL_SECONDS,
    }

    suggestion_key: str | None = None
    if body.get("suggested_id"):
        suggestion = find_suggestion(ctx, body["suggested_id"])
        if suggestion is None:
            return finish(_error(400, "invalid_request"), "rejected", error="invalid_request")
        question = str(suggestion["question"])
        focus_alias = suggestion["focus"]
        suggestion_key = f"S#{suggestion['id']}"
        base_item.update({"kind": "suggested", "suggestedId": suggestion["id"]})
        log["kind"] = "suggested"
        prior = _asked_suggestion(tables, review_id, suggestion["id"], now)
        if prior is not None:
            return finish(_success(prior, _remaining(review, limit), limit, admin), "replayed")
        stored = tables.questions.get_item({"reviewId": review_id, "questionKey": suggestion_key})
        if stored and question_is_live(stored, now) and stored.get("status") in FINAL_STATUSES:
            item = {
                **base_item,
                "ttl": min(base_item["ttl"], int(stored["ttl"])),
                "question": question,
                "status": stored["status"],
                "refusalReason": stored.get("refusalReason"),
                "answer": stored.get("answer") or [],
                "modelId": stored.get("modelId"),
                "promptVersion": stored.get("promptVersion"),
            }
            tables.questions.put_item(item)
            return finish(
                _success(item, _remaining(review, limit), limit, admin),
                "served_stored",
                status=stored["status"],
            )
    else:
        try:
            question = check_question(body.get("question"))
        except QuestionRejected as exc:
            return finish(_error(400, "invalid_question"), "rejected", error=exc.reason)
        focus_alias = None
        if body.get("focus_finding_id"):
            focus_alias = ctx.alias_for(body["focus_finding_id"])
            if focus_alias is None:
                return finish(_error(400, "invalid_request"), "rejected", error="invalid_request")
        base_item.update({"kind": "custom"})
        log["kind"] = "custom"

    model_id = os.environ.get("CHAT_MODEL_ID", DEFAULT_MODEL_ID)
    canary = os.environ.get("CHAT_CANARY", "")
    log.update({"model_id": model_id, "prompt_version": PROMPT_VERSION})
    prompt_chars = len(build_system_prompt(canary)) + len(ctx.cached_text()) + 12000
    reserve = reserve_micro_usd(model_id, prompt_chars, MAX_OUTPUT_TOKENS)
    log["reserve_micro_usd"] = reserve
    counts_slot = suggestion_key is None
    turned_away = _precheck(tables, review, admin, counts_slot, reserve, now)
    if turned_away:
        return finish(_error(429, turned_away), "rejected", error=turned_away)

    screening_claim = None
    screening_cost = 0
    if suggestion_key is None:
        screening_claim = uuid.uuid4().hex
        screening_cost = GUARDRAIL_INPUT_MICRO_USD_PER_UNIT
        screening_item = {
            **base_item,
            "question": question,
            "status": "screening",
            "screeningClaim": screening_claim,
        }
        refused = _admit(tables, review_id, screening_item, None, False, admin, screening_cost, now)
        if refused:
            code = {"request_in_progress": 409, "chat_busy": 503}.get(refused, 429)
            return finish(_error(code, refused), "rejected", error=refused)
        try:
            verdict = GuardrailsClient(
                guardrail_id=os.environ["CHAT_GUARDRAIL_ID"],
                guardrail_version=os.environ.get("CHAT_GUARDRAIL_VERSION", "1"),
                **_SMALL_CALL,
            ).assess(question)
        except Exception:  # noqa: BLE001 - fail closed: no screening, no model call
            # Keep the screening reservation: a timed-out request may be billed.
            _mark_failed(
                tables, review_id, [question_key], "guardrails_unavailable", screening_claim
            )
            return finish(
                _error(503, "guardrails_unavailable"), "rejected", error="guardrails_unavailable"
            )
        if verdict.blocked:
            fields = {
                "blocked_filters": verdict.filters,
                "question_sha256": question_hash(question),
                "est_cost_micro_usd": GUARDRAIL_INPUT_MICRO_USD_PER_UNIT,
            }
            max_blocked = _env_int("CHAT_BLOCKED_PER_REVIEW", DEFAULT_BLOCKED_PER_REVIEW)
            if not _record_blocked(tables, review_id, admin, max_blocked):
                _mark_failed(tables, review_id, [question_key], "too_many_blocked", screening_claim)
                return finish(
                    _error(429, "too_many_blocked"), "blocked", error="too_many_blocked", **fields
                )
            item = {
                **base_item,
                "question": question,
                "status": "refused",
                "costMicroUsd": screening_cost,
                "refusalReason": "blocked",
                "answer": [{"text": REFUSAL_TEXTS["blocked"], "citations": []}],
            }
            tables.questions.put_item(item)
            return finish(
                _success(item, _remaining(review, limit), limit, admin),
                "blocked",
                status="refused",
                refusal_reason="blocked",
                **fields,
            )

    question_item = {**base_item, "question": question, "status": "in_flight"}
    if screening_claim:
        question_item["screeningClaim"] = screening_claim
    if focus_alias:
        question_item["focusFindingId"] = ctx.finding_ids[focus_alias]
    history = [] if suggestion_key else _history(tables, review_id, question_key, now)
    refused = _admit(
        tables,
        review_id,
        question_item,
        suggestion_key,
        counts_slot,
        admin,
        reserve - screening_cost,
        now,
    )
    if refused == "request_in_progress":
        again = tables.questions.get_item({"reviewId": review_id, "questionKey": question_key})
        if again and question_is_live(again, now) and again.get("status") in FINAL_STATUSES:
            return finish(_success(again, _remaining(review, limit), limit, admin), "replayed")
    if refused:
        if screening_claim:
            _mark_failed(tables, review_id, [question_key], refused, screening_claim)
        status_code = {"request_in_progress": 409, "chat_busy": 503}.get(refused, 429)
        return finish(_error(status_code, refused), "rejected", error=refused)

    in_flight_keys = [question_key] + ([suggestion_key] if suggestion_key else [])
    try:
        clients = _clients(model_id)
        result = answer_question(ctx, question, history, focus_alias, clients, canary, deadline)
    except (ReadTimeoutError, ConnectTimeoutError):
        _mark_failed(tables, review_id, in_flight_keys, "answer_timeout")
        _record_failure(tables, review_id, refund=counts_slot)
        return finish(_error(504, "answer_timeout"), "failed", error="answer_timeout")
    except ClientError as exc:
        # Bedrock throttling or a service error: a plain, retryable
        # failure rather than a bare 500.
        code = exc.response.get("Error", {}).get("Code", "")
        _mark_failed(tables, review_id, in_flight_keys, "answer_failed")
        _record_failure(tables, review_id, refund=counts_slot)
        if code in RETRYABLE_BEDROCK_ERRORS:
            return finish(_error(503, "answer_failed"), "failed", error=code)
        raise
    except (ModelOutputTruncated, UnexpectedStopReason, ToolCallMissing, MalformedAnswer) as exc:
        _mark_failed(tables, review_id, in_flight_keys, "answer_failed")
        _record_failure(tables, review_id, refund=counts_slot)
        # Which check failed, and the stop reason when there is one; never
        # the model's text (stage 7 logs no question or answer text).
        failure = type(exc).__name__
        stop_reason = getattr(exc, "stop_reason", None)
        return finish(
            _error(502, "answer_failed"),
            "failed",
            error="answer_failed",
            failure=f"{failure}:{stop_reason}" if stop_reason else failure,
        )
    except Exception:
        _mark_failed(tables, review_id, in_flight_keys, "internal_error")
        _record_failure(tables, review_id, refund=counts_slot)
        raise

    result.cost_micro_usd += screening_cost
    answered_at = datetime.now(UTC).isoformat()
    stored_fields = {
        **_answer_fields(result.answer),
        "answeredAt": answered_at,
        "modelId": model_id,
        "promptVersion": PROMPT_VERSION,
        "inputTokens": result.usage.get("inputTokens", 0),
        "outputTokens": result.usage.get("outputTokens", 0),
        "cacheReadTokens": result.usage.get("cacheReadInputTokens", 0),
        "cacheWriteTokens": result.usage.get("cacheWriteInputTokens", 0),
        "costMicroUsd": result.cost_micro_usd,
        "citationsDropped": result.answer.citations_dropped,
    }
    item = {**question_item, **stored_fields}
    tables.questions.put_item(item)
    if suggestion_key:
        tables.questions.put_item(
            {
                "reviewId": review_id,
                "questionKey": suggestion_key,
                "createdAt": int(now),
                "ttl": base_item["ttl"],
                **stored_fields,
            }
        )
    _settle(tables, reserve, result.cost_micro_usd, now)

    used = int(review.get("questionsUsed", 0)) + (1 if counts_slot else 0)
    return finish(
        _success(item, max(0, limit - used), limit, admin),
        "answered",
        status=result.answer.status,
        refusal_reason=result.answer.refusal_reason,
        canary_hit=result.answer.canary_hit,
        citations_total=result.answer.citations_total,
        citations_dropped=result.answer.citations_dropped,
        retrieved_chunks=result.retrieved_chunks,
        grounding_score=result.grounding.get("GROUNDING"),
        relevance_score=result.grounding.get("RELEVANCE"),
        input_tokens=result.usage.get("inputTokens", 0),
        cache_read_tokens=result.usage.get("cacheReadInputTokens", 0),
        cache_write_tokens=result.usage.get("cacheWriteInputTokens", 0),
        output_tokens=result.usage.get("outputTokens", 0),
        est_cost_micro_usd=result.cost_micro_usd,
    )
