"""Evaluation-only request admission and durable attempt accounting.

These are service-call, request-size and dispatch-time limits, not a dollar
ceiling. Prices and service billing units are deliberately not guessed.
Production reports and their pricing have no dependency on this module.
"""

from __future__ import annotations

import argparse
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.shared.evaluation_manifest import evidence_manifest

METHODS = {
    "embed",
    "query_vectors",
    "check",
    "assess",
    "grounding_scores",
    "converse_structured",
    "converse_tool_cached",
}
USAGE_KEYS = {"inputTokens", "outputTokens", "cacheReadInputTokens", "cacheWriteInputTokens"}


class EvaluationLimitReached(RuntimeError):
    pass


def add_budget_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--max-generated-tokens",
        type=int,
        help="aggregate requested generation ceiling; failed calls keep their reservation",
    )
    parser.add_argument(
        "--max-paid-calls",
        type=int,
        help="required for paid runs: total service-call ceiling, including retrieval and guards",
    )
    parser.add_argument(
        "--max-seconds", type=int, default=300, help="stop admitting calls after this elapsed time"
    )
    parser.add_argument(
        "--max-request-bytes",
        type=int,
        default=128000,
        help="maximum serialized request size per call",
    )
    parser.add_argument(
        "--run-log",
        type=Path,
        help="private call journal; default is a unique ignored backend/build/evaluations file",
    )


def budget_plan(
    args: argparse.Namespace, parser: argparse.ArgumentParser, planned_calls: int
) -> dict:
    for name in ("max_paid_calls", "max_seconds", "max_request_bytes", "max_generated_tokens"):
        value = getattr(args, name)
        if value is not None and value <= 0:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    manifest = getattr(args, "evaluation_manifest", None)
    selected = sum(manifest["selected_set_sizes"].values()) if manifest else 0
    output_per_case = manifest["configuration"].get("max_output_tokens", 0) if manifest else 0
    planned_generation = selected * output_per_case
    if args.max_generated_tokens is not None and planned_generation > args.max_generated_tokens:
        parser.error(
            "selected scope exceeds --max-generated-tokens; reduce --limit or deliberately raise the cap"
        )
    return {
        "planned_service_calls_upper_bound": planned_calls,
        "max_paid_calls": args.max_paid_calls,
        "max_seconds": args.max_seconds,
        "max_request_bytes": args.max_request_bytes,
        "max_model_output_tokens_per_call": 8192,
        "monetary_limit_enforced": False,
        "max_generated_tokens": args.max_generated_tokens or planned_calls * 8192,
        "planned_output_token_upper_bound": planned_generation,
        "manifest": manifest,
    }


def admit_budget(
    args: argparse.Namespace, parser: argparse.ArgumentParser, planned_calls: int
) -> EvaluationBudget:
    plan = budget_plan(args, parser, planned_calls)
    if args.max_paid_calls is None:
        parser.error("paid runs require an explicit --max-paid-calls; inspect --plan first")
    if planned_calls > args.max_paid_calls:
        parser.error(
            "selected scope exceeds --max-paid-calls; reduce --limit or deliberately raise the cap"
        )
    path = (
        args.run_log
        or Path(__file__).resolve().parents[1] / "build/evaluations" / f"{uuid.uuid4().hex}.json"
    )
    if path.exists():
        parser.error("--run-log already exists; use a new file to preserve previous evidence")
    return EvaluationBudget(plan, path)


class EvaluationBudget:
    def __init__(self, plan: dict, path: Path, *, clock=time.monotonic):
        self.plan, self.path, self.clock = plan, path, clock
        self.started = clock()
        self.started_at = datetime.now(UTC).isoformat()
        self.calls: list[dict] = []
        self.stop_reason: str | None = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("x", encoding="utf-8") as journal:
            json.dump(self.summary(), journal, indent=2)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.summary(), indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def summary(self) -> dict:
        return {
            "version": "evaluation-admission@1",
            "limits": self.plan,
            "started_at": self.started_at,
            "dispatched_calls": len(self.calls),
            "stop_reason": self.stop_reason,
            "calls": self.calls,
            "reserved_output_tokens": sum(
                row.get("reserved_output_tokens", 0) for row in self.calls
            ),
        }

    def _deny(self, reason: str) -> None:
        self.stop_reason = reason
        self._save()
        raise EvaluationLimitReached(reason)

    def wrap(self, client: Any, service: str) -> Any:
        return _BudgetedClient(client, service, self)

    def invoke(self, client: Any, service: str, method: str, args: tuple, kwargs: dict) -> Any:
        if self.stop_reason:
            raise EvaluationLimitReached(self.stop_reason)
        if len(self.calls) >= self.plan["max_paid_calls"]:
            self._deny("call_limit")
        if self.clock() - self.started >= self.plan["max_seconds"]:
            self._deny("dispatch_deadline")
        size = len(json.dumps([args, kwargs], ensure_ascii=False, default=str).encode())
        if size > self.plan["max_request_bytes"]:
            self._deny("request_size_limit")
        if method.startswith("converse") and (
            args
            or type(kwargs.get("max_tokens")) is not int
            or not 0 < kwargs["max_tokens"] <= self.plan["max_model_output_tokens_per_call"]
        ):
            self._deny("output_token_limit")
        reserved = kwargs["max_tokens"] if method.startswith("converse") else 0
        total = sum(row.get("reserved_output_tokens", 0) for row in self.calls)
        ceiling = self.plan.get(
            "max_generated_tokens",
            self.plan["max_paid_calls"] * self.plan["max_model_output_tokens_per_call"],
        )
        if total + reserved > ceiling:
            self._deny("generated_token_limit")
        # An attempt remains counted on timeout, malformed output or interruption.
        # Persist before dispatch so a killed process leaves evidence of uncertainty.
        row = {
            "operation": f"{service}.{method}",
            "outcome": "started",
            "request_bytes": size,
            "usage": None,
            "reserved_output_tokens": reserved,
            "started_at": datetime.now(UTC).isoformat(),
        }
        self.calls.append(row)
        self._save()
        sdk = getattr(client, "_client", None)
        events = getattr(getattr(sdk, "meta", None), "events", None)
        identity = f"evaluation-usage-{uuid.uuid4().hex}"

        def capture(parsed, **_):
            usage = parsed.get("usage") if isinstance(parsed, dict) else None
            if isinstance(usage, dict):
                row["usage"] = {
                    key: value
                    for key, value in usage.items()
                    if key in USAGE_KEYS and type(value) is int and value >= 0
                }

        if events is not None:
            events.register("after-call", capture, unique_id=identity)
        try:
            result = getattr(client, method)(*args, **kwargs)
            if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], dict):
                capture({"usage": result[1]})
            if method == "query_vectors" and isinstance(result, list):
                row["retrieved_evidence"] = evidence_manifest(
                    [item.get("metadata", {}) for item in result if isinstance(item, dict)]
                )
            row["outcome"] = "returned"
            return result
        except BaseException as exc:
            row["outcome"] = "failed"
            row["error_kind"] = type(exc).__name__
            raise
        finally:
            row["finished_at"] = datetime.now(UTC).isoformat()
            if events is not None:
                events.unregister("after-call", unique_id=identity)
            self._save()


class _BudgetedClient:
    def __init__(self, client: Any, service: str, budget: EvaluationBudget):
        self._wrapped, self._service, self._budget = client, service, budget

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        value = getattr(self._wrapped, name)
        if not callable(value):
            return value
        if name not in METHODS:
            self._budget._deny("unbudgeted_operation")
        return lambda *args, **kwargs: self._budget.invoke(
            self._wrapped, self._service, name, args, kwargs
        )
