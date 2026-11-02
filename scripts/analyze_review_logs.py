"""Per-review health report from the AgentCore runtime's CloudWatch logs.

Run from the repo root:
    python scripts/analyze_review_logs.py --profile archibrief-deploy --hours 24
    python scripts/analyze_review_logs.py --hours 72 --json

Each review runs in its own runtime session, and each session writes its
own log stream, so a stream is one review. The script reads the size-only
events the runtime logs (reasoning_input, reasoning_call,
reasoning_call_failed, reasoning_result) and AgentCore's invocation lines,
and reports for each review whether the model step finished, how long it
took, its tokens and estimated cost, how many findings survived and why
any were rejected. It also flags the failures found by hand during
debugging: calls cut off by the read timeout, answers near max_tokens, and
runtime crashes such as a missing module.

The logs hold sizes and counts only, never review content, so neither does
this report. Costs are estimates from backend/chat/pricing.py, not billing.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.chat.pricing import model_cost_micro_usd

LOG_GROUP_PREFIX = "/aws/bedrock-agentcore/runtimes/archibrief_dev-"
DEFAULT_MODEL_ID = "us.anthropic.claude-sonnet-4-6"
_SESSION = re.compile(r"archibrief-(review|deeper-review)-session-([0-9a-f-]{36})")
_INVOCATION = re.compile(r"Invocation (completed successfully|failed) \(([\d.]+)s\)")
_CRASH = re.compile(r"^(\w+(?:Error|Exception)): ")
_EVENTS = {
    "reasoning_input",
    "reasoning_call",
    "reasoning_call_failed",
    "reasoning_result",
}


@dataclass
class ReviewRun:
    review_id: str
    kind: str
    started: int = 0
    outcome: str = "no model call"
    invocation_seconds: float | None = None
    input_chars: int | None = None
    resources_sent: int | None = None
    resources_truncated: bool = False
    evidence_passages: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    model_seconds: float | None = None
    near_max_tokens: bool = False
    failure: str | None = None
    emitted: int | None = None
    capped: int = 0
    accepted: int | None = None
    rejected: dict[str, int] = field(default_factory=dict)
    crash: str | None = None
    cost_usd: float | None = None


def _json(message: str) -> dict | None:
    if not message.startswith("{"):
        return None
    try:
        value = json.loads(message)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def summarize_stream(
    stream_name: str, events: list[dict], model_id: str
) -> ReviewRun | None:
    """One review's run from its log stream's events ({timestamp, message})."""
    match = _SESSION.search(stream_name)
    if not match:
        return None
    run = ReviewRun(review_id=match.group(2), kind=match.group(1))
    run.started = min((e["timestamp"] for e in events), default=0)
    for event in sorted(events, key=lambda e: e["timestamp"]):
        message = event["message"].strip()
        if invocation := _INVOCATION.search(message):
            run.invocation_seconds = float(invocation.group(2))
            if invocation.group(1) == "failed" and run.outcome == "no model call":
                run.outcome = "runtime failed"
            continue
        if _CRASH.match(message):
            run.crash = message[:160]
            run.outcome = "runtime crashed"
            continue
        data = _json(message)
        name = data.get("event") if data else None
        if name not in _EVENTS:
            continue
        if name == "reasoning_input":
            run.input_chars = data.get("chars")
            run.resources_sent = data.get("resources_sent")
            run.resources_truncated = bool(data.get("resources_truncated"))
            run.evidence_passages = data.get("evidence_passages")
        elif name == "reasoning_call":
            run.input_tokens = data.get("input_tokens")
            run.output_tokens = data.get("output_tokens")
            latency = data.get("elapsed_ms") or data.get("latency_ms")
            run.model_seconds = latency / 1000 if latency else None
            run.near_max_tokens = bool(data.get("near_max_tokens"))
            stop = data.get("stop_reason")
            run.outcome = "finished" if stop == "tool_use" else f"stopped: {stop}"
            run.cost_usd = (
                model_cost_micro_usd(
                    model_id,
                    {
                        "inputTokens": run.input_tokens or 0,
                        "outputTokens": run.output_tokens or 0,
                    },
                )
                / 1_000_000
            )
        elif name == "reasoning_call_failed":
            run.outcome = "model call failed"
            elapsed = data.get("elapsed_ms")
            run.model_seconds = elapsed / 1000 if elapsed else None
            run.failure = data.get("kind")
        elif name == "reasoning_result":
            run.emitted = data.get("emitted")
            run.capped = data.get("capped") or 0
            run.accepted = data.get("accepted")
            run.rejected = data.get("rejected") or {}
    return run


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))]


def _mean(values: list[int | None]) -> int | None:
    known = [v for v in values if v]
    return round(statistics.mean(known)) if known else None


def overview(runs: list[ReviewRun]) -> dict:
    """Totals across runs, and what deserves attention."""
    finished = [r for r in runs if r.outcome == "finished"]
    seconds = [r.model_seconds for r in finished if r.model_seconds]
    rejected: Counter[str] = Counter()
    for run in runs:
        rejected.update(run.rejected)
    attention = []
    for run in runs:
        reasons = []
        if run.outcome != "finished":
            reasons.append(run.outcome + (f" ({run.failure})" if run.failure else ""))
        if run.crash:
            reasons.append(run.crash)
        if run.near_max_tokens:
            reasons.append(
                "answer near max_tokens: raise it before answers get cut off"
            )
        if run.resources_truncated:
            reasons.append("resource summary truncated")
        if run.capped:
            reasons.append(f"{run.capped} model findings past the cap")
        if reasons:
            attention.append({"review_id": run.review_id, "reasons": reasons})
    return {
        "reviews": len(runs),
        "model_finished": len(finished),
        "success_rate": round(len(finished) / len(runs), 3) if runs else None,
        "model_seconds_p50": _percentile(seconds, 0.5),
        "model_seconds_p95": _percentile(seconds, 0.95),
        "model_seconds_max": max(seconds, default=None),
        "input_tokens_mean": _mean([r.input_tokens for r in finished]),
        "output_tokens_mean": _mean([r.output_tokens for r in finished]),
        "estimated_cost_usd": round(sum(r.cost_usd or 0 for r in runs), 2),
        "findings_accepted": sum(r.accepted or 0 for r in runs),
        "findings_rejected_by_kind": dict(rejected),
        "needs_attention": attention,
    }


def _fmt(value: object, suffix: str = "") -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.0f}{suffix}" if value >= 10 else f"{value:.1f}{suffix}"
    return f"{value}{suffix}"


def render(runs: list[ReviewRun], totals: dict) -> str:
    header = (
        f"{'started (UTC)':<17} {'review':<9} {'outcome':<18} {'model':>6} {'in tok':>7} "
        f"{'out tok':>7} {'found':>5} {'rej':>4} {'cost':>6}"
    )
    lines = [header]
    for run in sorted(runs, key=lambda r: r.started):
        started = time.strftime("%m-%d %H:%M:%S", time.gmtime(run.started / 1000))
        cost = f"${run.cost_usd:.2f}" if run.cost_usd is not None else "-"
        lines.append(
            f"{started:<17} {run.review_id[:8]:<9} {run.outcome[:18]:<18} "
            f"{_fmt(run.model_seconds, 's'):>6} {_fmt(run.input_tokens):>7} "
            f"{_fmt(run.output_tokens):>7} {_fmt(run.accepted):>5} "
            f"{sum(run.rejected.values()):>4} {cost:>6}"
        )
    finished = (
        f"{totals['model_finished']} of {totals['reviews']} reviews finished the model step "
        f"(success rate {_fmt(totals['success_rate'])})."
    )
    timing = (
        f"Model time p50 {_fmt(totals['model_seconds_p50'], 's')}, "
        f"p95 {_fmt(totals['model_seconds_p95'], 's')}, "
        f"max {_fmt(totals['model_seconds_max'], 's')}; "
        f"mean tokens in {_fmt(totals['input_tokens_mean'])}, "
        f"out {_fmt(totals['output_tokens_mean'])}."
    )
    findings = (
        f"Estimated model cost ${totals['estimated_cost_usd']:.2f}; "
        f"{totals['findings_accepted']} model findings kept; rejected by kind: "
        f"{totals['findings_rejected_by_kind'] or 'none'}."
    )
    lines += ["", finished, timing, findings]
    if totals["needs_attention"]:
        lines += ["", "Needs attention:"]
        for item in totals["needs_attention"]:
            lines.append(f"  {item['review_id'][:8]}: " + "; ".join(item["reasons"]))
    return "\n".join(lines)


def fetch_streams(
    logs, log_group: str, since_ms: int
) -> dict[str, list[dict]]:  # pragma: no cover - AWS
    """Every event of every stream written since `since_ms`, by stream."""
    streams: dict[str, list[dict]] = {}
    paginator = logs.get_paginator("filter_log_events")
    for page in paginator.paginate(logGroupName=log_group, startTime=since_ms):
        for event in page.get("events", []):
            streams.setdefault(event["logStreamName"], []).append(
                {"timestamp": event["timestamp"], "message": event["message"]}
            )
    return streams


def main() -> int:  # pragma: no cover - AWS
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--profile", default="archibrief-deploy")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--hours", type=float, default=24)
    parser.add_argument(
        "--log-group", help="defaults to the archibrief_dev runtime's group"
    )
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument(
        "--json", action="store_true", help="print JSON instead of a table"
    )
    args = parser.parse_args()

    import boto3

    logs = boto3.Session(profile_name=args.profile, region_name=args.region).client(
        "logs"
    )
    log_group = args.log_group
    if not log_group:
        groups = logs.describe_log_groups(logGroupNamePrefix=LOG_GROUP_PREFIX)[
            "logGroups"
        ]
        if not groups:
            parser.error(
                f"no log group starts with {LOG_GROUP_PREFIX}; pass --log-group"
            )
        log_group = groups[0]["logGroupName"]
    since_ms = int((time.time() - args.hours * 3600) * 1000)
    runs = [
        run
        for name, events in fetch_streams(logs, log_group, since_ms).items()
        if (run := summarize_stream(name, events, args.model_id)) is not None
    ]
    totals = overview(runs)
    if args.json:
        print(
            json.dumps(
                {"runs": [asdict(r) for r in runs], "overview": totals}, indent=2
            )
        )
    else:
        print(render(runs, totals))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
