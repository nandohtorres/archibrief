"""P1 small-workload baseline runner (pilot plan P1; audit F10, F11, F14).

The owner submits each review on the live site: uploads need a Turnstile
token, and the plan forbids a separate, unmetered evaluation entry point.
So what is measured is the production path with production settings
(F11). This script freezes the batch plan, gates every next submission on
what has actually been spent (F10), and collects and scores the results,
keeping raw, capped and rejected finding counts (F14).

Run from the repo root, in order:

    python scripts/small_workload_eval.py plan
    python scripts/small_workload_eval.py approve --plan-hash <hash>
    python scripts/small_workload_eval.py gate          # before every submission
    python scripts/small_workload_eval.py record --slot 1 --review-id <uuid>
    python scripts/small_workload_eval.py collect       # ledgers + log metrics
    python scripts/small_workload_eval.py worksheet     # judging sheet
    python scripts/small_workload_eval.py score         # after judging

Everything it writes is private (backend/build/evaluations/p1/, ignored):
ledgers hold submitted Terraform facts and model text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "backend" / "fixtures" / "small_workloads"
OUT = ROOT / "backend" / "build" / "evaluations" / "p1"

# Contract section 10: every input once, then T3a's repeat, then the T1/T2
# repeats. Failures use their slot; there are no automatic replacements.
SCHEDULE: tuple[str, ...] = (
    "T1-small",
    "T1-full",
    "T2-small",
    "T2-full",
    "T3a",
    "T3b-neutral",
    "T3b-hostile",
    "T3a",
    "T1-full",
    "T2-full",
    "T1-full",
    "T2-full",
)
HELD_OUT = frozenset({"T3b-neutral", "T3b-hostile"})
SEVERITIES = ("Critical", "High", "Medium", "Low")

RESERVATION_USD = 0.40  # per review, the production admission reservation
BATCH_APPROVAL_USD = 5.00  # owner's batch spend approval
# Production settings the baseline must match (runtime_entrypoint.py,
# infra/modules/agentcore-runtime/variables.tf). Recorded in the plan.
PRODUCTION_MODEL_ID = "us.anthropic.claude-sonnet-4-6"
PRODUCTION_MAX_OUTPUT_TOKENS = 12_288
# Above this input size a full-length answer no longer fits the $0.40
# reservation at Sonnet 4.6 US prices ($3.30/M in, $16.50/M out):
# 12,288 out = $0.203, leaving about 59.7k input tokens. Stop short of it.
STOP_INPUT_TOKENS = 55_000
# Everything billed besides the model call: Guardrails on the brief (up to
# 4 text units, up to 3 ingest attempts at $0.0003), retrieval embeddings
# and vector queries. A deliberately generous fixed allowance.
OTHER_BILLED_USD = 0.01
CHECKPOINT_RECALL = 0.80  # Critical/High; below it, diagnose before P3b

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class PlanError(RuntimeError):
    """A plan, journal or worksheet that must not be used as is."""


# ---------------------------------------------------------------- helpers


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PlanError(f"missing {path.relative_to(ROOT)}") from exc
    if not isinstance(value, dict):
        raise PlanError(f"{path.relative_to(ROOT)} is not a JSON object")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# ------------------------------------------------------------------ corpus


def load_manifest(corpus: Path = CORPUS) -> dict:
    """The corpus manifest, with every listed file's hash verified and every
    scheduled case present. Raises PlanError on any mismatch."""
    manifest = _read_json(corpus / "manifest.json")
    files = manifest.get("files")
    cases = manifest.get("cases")
    if not isinstance(files, dict) or not files or not isinstance(cases, list):
        raise PlanError("manifest needs a non-empty 'files' map and a 'cases' list")
    for relative, expected in files.items():
        path = corpus / relative
        if not path.is_file():
            raise PlanError(f"manifest lists a missing file: {relative}")
        if sha256_file(path) != expected:
            raise PlanError(
                f"hash mismatch (corpus changed after freezing): {relative}"
            )
    by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
    missing = sorted(set(SCHEDULE) - set(by_id))
    if missing:
        raise PlanError(f"manifest is missing scheduled cases: {', '.join(missing)}")
    for case_id in set(SCHEDULE):
        case = by_id[case_id]
        for key in ("dir", "brief", "oracle", "declarations"):
            if key not in case:
                raise PlanError(f"case {case_id} has no '{key}'")
        for key in ("brief", "oracle"):
            if case[key] not in files:
                raise PlanError(f"case {case_id}: {case[key]} is not hash-listed")
    return manifest


def case_by_id(manifest: dict) -> dict[str, dict]:
    return {case["id"]: case for case in manifest["cases"]}


def load_oracle(corpus: Path, case: dict) -> dict:
    oracle = _read_json(corpus / case["oracle"])
    issues = oracle.get("issues")
    if not isinstance(issues, list) or not issues:
        raise PlanError(f"{case['oracle']}: needs a non-empty 'issues' list")
    seen: set[str] = set()
    for issue in issues:
        if not isinstance(issue, dict) or not {"id", "severity", "address"} <= set(
            issue
        ):
            raise PlanError(
                f"{case['oracle']}: every issue needs id, severity, address"
            )
        if issue["severity"] not in SEVERITIES:
            raise PlanError(f"{case['oracle']}: {issue['id']} has unknown severity")
        if issue["id"] in seen:
            raise PlanError(f"{case['oracle']}: duplicate issue id {issue['id']}")
        seen.add(issue["id"])
    if not isinstance(oracle.get("safe_counterexamples", []), list):
        raise PlanError(f"{case['oracle']}: 'safe_counterexamples' must be a list")
    return oracle


def must_find(issue: dict) -> bool:
    """Critical/High issues are must-find unless the oracle says otherwise."""
    return bool(issue.get("must_find", issue["severity"] in ("Critical", "High")))


def local_input_estimate(
    case_dir: Path,
) -> dict:  # pragma: no cover - needs HCL parsing
    """Declarations and the locally known part of the model input (resource
    summary plus rule findings), computed with the deployed code. Retrieved
    guidance is added by the runtime and is not known until it runs."""
    sys.path.insert(0, str(ROOT))
    from backend.lambdas.ingest.handler import parse_terraform_files
    from backend.lambdas.rule_engine.handler import run_rules
    from backend.lambdas.rule_engine.resource_summary import build_resource_summary

    files = sorted(str(p) for p in case_dir.rglob("*.tf"))
    parsed = asdict(parse_terraform_files(files, archive_root=str(case_dir)))
    findings = run_rules(parsed, "p1-plan")
    summary = build_resource_summary(parsed)
    scope = parsed.get("review_scope") or {}
    return {
        "known_y": scope.get("known_y"),
        "scope_state": scope.get("state"),
        "summary_chars": len(json.dumps(summary)),
        "rule_findings": len(findings),
        "rule_finding_chars": len(
            json.dumps([f.model_dump(mode="json") for f in findings])
        ),
    }


def _git_head() -> str:  # pragma: no cover - subprocess
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def build_plan(manifest: dict, estimates: dict[str, dict], code_revision: str) -> dict:
    """The frozen batch plan. Its hash is what the owner approves."""
    cases = case_by_id(manifest)
    for case_id in set(SCHEDULE):
        known = estimates[case_id].get("known_y")
        if known != cases[case_id]["declarations"]:
            raise PlanError(
                f"{case_id}: manifest says {cases[case_id]['declarations']} declarations, "
                f"the deployed parser counts {known}"
            )
    body = {
        "schedule": [
            {"slot": n, "case": case_id, "held_out": case_id in HELD_OUT}
            for n, case_id in enumerate(SCHEDULE, start=1)
        ],
        "corpus_files": manifest["files"],
        "configuration": {
            "path": "production (live site, owner-submitted)",
            "model_id": PRODUCTION_MODEL_ID,
            "max_output_tokens": PRODUCTION_MAX_OUTPUT_TOKENS,
            "code_revision": code_revision,
        },
        "budget": {
            "reviews": len(SCHEDULE),
            "reservation_usd_each": RESERVATION_USD,
            "reserved_usd": round(len(SCHEDULE) * RESERVATION_USD, 2),
            "approval_usd": BATCH_APPROVAL_USD,
            "stop_input_tokens": STOP_INPUT_TOKENS,
            "other_billed_usd_each": OTHER_BILLED_USD,
        },
        "estimates": estimates,
    }
    return {**body, "plan_hash": canonical_hash(body), "created_at": _now()}


# ----------------------------------------------------------------- journal


def new_journal(plan: dict) -> dict:
    return {"plan_hash": plan["plan_hash"], "approved_at": None, "slots": {}}


def approve(journal: dict, plan: dict, plan_hash: str) -> dict:
    if plan_hash != plan["plan_hash"] or journal["plan_hash"] != plan["plan_hash"]:
        raise PlanError(
            "that hash is not the current plan's; re-run plan and read it again"
        )
    return {**journal, "approved_at": _now()}


def next_slot(journal: dict) -> int | None:
    done = {int(n) for n in journal["slots"]}
    return next((n for n in range(1, len(SCHEDULE) + 1) if n not in done), None)


def record(journal: dict, slot: int, review_id: str) -> dict:
    if not journal.get("approved_at"):
        raise PlanError("the plan is not approved; no review may be submitted")
    expected = next_slot(journal)
    if expected is None:
        raise PlanError("all slots are used; extra runs need owner approval")
    if slot != expected:
        raise PlanError(f"slots are used in order; the next is {expected}")
    if not _UUID.match(review_id):
        raise PlanError("review id must be a lowercase UUID")
    if any(entry["review_id"] == review_id for entry in journal["slots"].values()):
        raise PlanError("that review is already recorded")
    slots = {
        **journal["slots"],
        str(slot): {
            "case": SCHEDULE[slot - 1],
            "review_id": review_id,
            "recorded_at": _now(),
        },
    }
    return {**journal, "slots": slots}


# -------------------------------------------------------------------- gate


def slot_cost(run: dict | None) -> tuple[float, bool]:
    """(estimated USD, known). A review with no finished model call in the
    logs keeps its whole reservation: a failure after the call started does
    not prove nothing was billed, and never counts as zero."""
    if not run or run.get("cost_usd") is None:
        return RESERVATION_USD, False
    return run["cost_usd"] + OTHER_BILLED_USD, True


def gate(journal: dict, runs: dict[str, dict]) -> dict:
    """Whether the next submission may go ahead, from what was actually
    spent. `runs` maps review id to analyze_review_logs' ReviewRun dict."""
    spent = 0.0
    stops: list[str] = []
    pending: list[int] = []
    for n, entry in sorted(journal["slots"].items(), key=lambda item: int(item[0])):
        run = runs.get(entry["review_id"])
        cost, known = slot_cost(run)
        spent += cost
        if run is None:
            pending.append(int(n))
            continue
        if known and cost > RESERVATION_USD:
            stops.append(
                f"slot {n} cost ${cost:.2f}, over its ${RESERVATION_USD:.2f} reservation"
            )
        if (run.get("input_tokens") or 0) > STOP_INPUT_TOKENS:
            stops.append(
                f"slot {n} sent {run['input_tokens']} input tokens (> {STOP_INPUT_TOKENS})"
            )
        if run.get("near_max_tokens"):
            stops.append(f"slot {n} answer reached the output-token limit")
    upcoming = next_slot(journal)
    if not journal.get("approved_at"):
        stops.append("plan not approved")
    if upcoming is None:
        stops.append("all slots used")
    elif spent + RESERVATION_USD > BATCH_APPROVAL_USD:
        stops.append(
            f"next reservation would exceed the ${BATCH_APPROVAL_USD:.2f} approval"
        )
    return {
        "spent_usd": round(spent, 4),
        "remaining_usd": round(BATCH_APPROVAL_USD - spent, 4),
        "next_slot": upcoming,
        "next_case": SCHEDULE[upcoming - 1] if upcoming else None,
        "pending_slots": pending,
        "go": not stops and not pending,
        "stops": stops,
    }


# --------------------------------------------------------------- worksheet


def _name_of(address: str) -> str:
    return address.rsplit(".", 1)[-1]


def candidates(issue_address: str, findings: list[dict]) -> list[str]:
    """Findings whose text mentions the issue's resource name: a starting
    point for the judge, never a verdict."""
    name = _name_of(issue_address)
    pattern = re.compile(rf"(?<![A-Za-z0-9_-]){re.escape(name)}(?![A-Za-z0-9_-])")
    return [
        f["finding_id"]
        for f in findings
        if pattern.search(json.dumps([f.get("evidence"), f.get("finding")]))
    ]


def build_worksheet(
    journal: dict, ledgers: dict[str, dict], oracles: dict[str, dict]
) -> dict:
    rows: list[dict] = []
    findings_to_judge: list[dict] = []
    for n, entry in sorted(journal["slots"].items(), key=lambda item: int(item[0])):
        ledger = ledgers.get(n)
        if ledger is None:
            continue
        oracle = oracles[entry["case"]]
        findings = ledger.get("findings", [])
        for issue in oracle["issues"]:
            rows.append(
                {
                    "slot": int(n),
                    "case": entry["case"],
                    "issue_id": issue["id"],
                    "severity": issue["severity"],
                    "must_find": must_find(issue),
                    "candidates": candidates(issue["address"], findings),
                    "caught_by": None,  # finding id, or "missed"
                    "note": "",
                }
            )
        counter_names = {
            _name_of(c["address"])
            for c in oracle.get("safe_counterexamples", [])
            if "address" in c
        }
        for finding in findings:
            text = json.dumps([finding.get("evidence"), finding.get("finding")])
            findings_to_judge.append(
                {
                    "slot": int(n),
                    "finding_id": finding["finding_id"],
                    "type": finding.get("type"),
                    "touches_counterexample": any(
                        name in text for name in counter_names
                    ),
                    # "valid" | "false_claim" | "duplicate" | "out_of_oracle"
                    "verdict": None,
                    "unsafe_fix": None,  # true when the remediation would cause harm
                }
            )
    return {
        "plan_hash": journal["plan_hash"],
        "issues": rows,
        "findings": findings_to_judge,
    }


# ------------------------------------------------------------------- score


def _ratio(hit: int, total: int) -> float | None:
    return round(hit / total, 3) if total else None


def score(
    journal: dict, worksheet: dict, ledgers: dict[str, dict], runs: dict[str, dict]
) -> dict:
    """The baseline report. Refuses a partly judged worksheet: a partial
    evaluation is never reported as a result."""
    if worksheet.get("plan_hash") != journal["plan_hash"]:
        raise PlanError("worksheet belongs to a different plan")
    open_issues = [r for r in worksheet["issues"] if r["caught_by"] is None]
    open_findings = [
        f
        for f in worksheet["findings"]
        if f["verdict"] is None or f["unsafe_fix"] is None
    ]
    if open_issues or open_findings:
        raise PlanError(
            f"judging incomplete: {len(open_issues)} issues and "
            f"{len(open_findings)} findings have no verdict"
        )
    slots: list[dict] = []
    for n, entry in sorted(journal["slots"].items(), key=lambda item: int(item[0])):
        run = runs.get(entry["review_id"]) or {}
        ledger = ledgers.get(n)
        issues = [r for r in worksheet["issues"] if str(r["slot"]) == n]
        judged = [f for f in worksheet["findings"] if str(f["slot"]) == n]
        crit_high = [
            r
            for r in issues
            if r["severity"] in ("Critical", "High") and r["must_find"]
        ]
        scope = (ledger or {}).get("review_scope") or {}
        cost, cost_known = slot_cost(run or None)
        slots.append(
            {
                "slot": int(n),
                "case": entry["case"],
                "held_out": entry["case"] in HELD_OUT,
                "completed": ledger is not None,
                "model_outcome": scope.get("model_outcome"),
                "critical_high_caught": sum(
                    r["caught_by"] != "missed" for r in crit_high
                ),
                "critical_high_total": len(crit_high),
                "all_caught": sum(r["caught_by"] != "missed" for r in issues),
                "all_total": len(issues),
                "false_claims": sum(f["verdict"] == "false_claim" for f in judged),
                "unsafe_fixes": sum(bool(f["unsafe_fix"]) for f in judged),
                "findings": len(judged),
                "scope": {
                    k: scope.get(k)
                    for k in ("known_y", "x", "sent_count", "categories")
                },
                "model": {
                    "emitted": run.get("emitted"),
                    "capped": run.get("capped"),
                    "accepted": run.get("accepted"),
                    "rejected": run.get("rejected"),
                    "input_tokens": run.get("input_tokens"),
                    "output_tokens": run.get("output_tokens"),
                    "seconds": run.get("model_seconds"),
                },
                "cost_usd": round(cost, 4),
                "cost_known": cost_known,
            }
        )
    summary: dict[str, dict] = {}
    for split, members in (
        ("development", [s for s in slots if not s["held_out"]]),
        ("held_out", [s for s in slots if s["held_out"]]),
    ):
        caught = sum(s["critical_high_caught"] for s in members)
        total = sum(s["critical_high_total"] for s in members)
        summary[split] = {
            "reviews": len(members),
            "failed_or_incomplete": sum(not s["completed"] for s in members),
            "critical_high_recall": _ratio(caught, total),
            "all_severity_recall": _ratio(
                sum(s["all_caught"] for s in members),
                sum(s["all_total"] for s in members),
            ),
            "false_claims": sum(s["false_claims"] for s in members),
            "unsafe_fixes": sum(s["unsafe_fixes"] for s in members),
        }
    dev_recall = summary["development"]["critical_high_recall"]
    return {
        "plan_hash": journal["plan_hash"],
        "slots": slots,
        "summary": summary,
        "spent_usd": round(sum(s["cost_usd"] for s in slots), 4),
        "checkpoint": {
            "critical_high_recall_target": CHECKPOINT_RECALL,
            "below": dev_recall is not None and dev_recall < CHECKPOINT_RECALL,
            "meaning": "below the target: diagnose every miss by stage before P3b; not a stop",
        },
        "release_gates": {
            "zero_false_claims": all(s["false_claims"] == 0 for s in slots),
            "zero_unsafe_fixes": all(s["unsafe_fixes"] == 0 for s in slots),
        },
        "generated_at": _now(),
    }


# --------------------------------------------------------------------- AWS


def _session(profile: str, region: str):  # pragma: no cover - AWS
    import boto3

    return boto3.Session(profile_name=profile, region_name=region)


def fetch_runs(
    session, review_ids: set[str], since_ms: int
) -> dict[str, dict]:  # pragma: no cover
    """analyze_review_logs' per-review runs for the given reviews."""
    sys.path.insert(0, str(ROOT))
    from scripts.analyze_review_logs import (
        LOG_GROUP_PREFIX,
        fetch_streams,
        summarize_stream,
    )

    logs = session.client("logs")
    groups = logs.describe_log_groups(logGroupNamePrefix=LOG_GROUP_PREFIX)["logGroups"]
    if not groups:
        raise PlanError(f"no log group starts with {LOG_GROUP_PREFIX}")
    runs: dict[str, dict] = {}
    for name, events in fetch_streams(
        logs, groups[0]["logGroupName"], since_ms
    ).items():
        run = summarize_stream(name, events, PRODUCTION_MODEL_ID)
        if run is not None and run.kind == "review" and run.review_id in review_ids:
            runs[run.review_id] = asdict(run)
    return runs


def _since_ms(journal: dict) -> int:
    stamps = [e["recorded_at"] for e in journal["slots"].values()]
    if not stamps:
        return int(time.time() * 1000)
    first = min(datetime.fromisoformat(s) for s in stamps)
    return int(first.timestamp() * 1000) - 2 * 3600 * 1000  # submitted before recording


# --------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI and AWS
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--profile", default="archibrief-deploy")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--bucket", default="archibrief-dev-source-of-truth")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan")
    approve_cmd = sub.add_parser("approve")
    approve_cmd.add_argument("--plan-hash", required=True)
    sub.add_parser("gate")
    record_cmd = sub.add_parser("record")
    record_cmd.add_argument("--slot", type=int, required=True)
    record_cmd.add_argument("--review-id", required=True)
    sub.add_parser("collect")
    sub.add_parser("worksheet")
    sub.add_parser("score")
    args = parser.parse_args(argv)

    plan_path, journal_path = OUT / "plan.json", OUT / "journal.json"
    try:
        if args.command == "plan":
            manifest = load_manifest()
            cases = case_by_id(manifest)
            for case_id in set(SCHEDULE):
                load_oracle(CORPUS, cases[case_id])
            estimates = {
                case_id: local_input_estimate(CORPUS / cases[case_id]["dir"])
                for case_id in sorted(set(SCHEDULE))
            }
            plan = build_plan(manifest, estimates, _git_head())
            if journal_path.exists() and _read_json(journal_path)["slots"]:
                raise PlanError("a batch is already in progress; the plan is frozen")
            _write_json(plan_path, plan)
            _write_json(journal_path, new_journal(plan))
            print(
                json.dumps(
                    {k: plan[k] for k in ("budget", "configuration", "estimates")},
                    indent=2,
                )
            )
            print(
                f"\nplan_hash {plan['plan_hash']}\nNot approved. Review, then run approve."
            )
        elif args.command == "approve":
            journal = approve(
                _read_json(journal_path), _read_json(plan_path), args.plan_hash
            )
            _write_json(journal_path, journal)
            print("approved; run gate before every submission")
        elif args.command == "record":
            journal = record(_read_json(journal_path), args.slot, args.review_id)
            _write_json(journal_path, journal)
            print(f"slot {args.slot} recorded as {SCHEDULE[args.slot - 1]}")
        else:
            journal = _read_json(journal_path)
            session = _session(args.profile, args.region)
            ids = {e["review_id"] for e in journal["slots"].values()}
            runs = fetch_runs(session, ids, _since_ms(journal)) if ids else {}
            if args.command == "gate":
                result = gate(journal, runs)
                print(json.dumps(result, indent=2))
                print("\nGO: submit", result["next_case"]) if result["go"] else print(
                    "\nDO NOT SUBMIT"
                )
                return 0 if result["go"] else 2
            if args.command == "collect":
                s3 = session.client("s3")
                for n, entry in journal["slots"].items():
                    key = f"reports/{entry['review_id']}/evidence-ledger.json"
                    try:
                        body = s3.get_object(Bucket=args.bucket, Key=key)["Body"].read()
                    except s3.exceptions.NoSuchKey:
                        print(f"slot {n}: no ledger (failed or not finished)")
                        continue
                    _write_json(OUT / "ledgers" / f"{n}.json", json.loads(body))
                _write_json(OUT / "runs.json", runs)
                print(f"collected {len(journal['slots'])} slots")
                return 0
            ledgers = {
                p.stem: _read_json(p) for p in sorted((OUT / "ledgers").glob("*.json"))
            }
            manifest = load_manifest()
            cases = case_by_id(manifest)
            oracles = {cid: load_oracle(CORPUS, cases[cid]) for cid in set(SCHEDULE)}
            if args.command == "worksheet":
                path = OUT / "worksheet.json"
                if path.exists():
                    raise PlanError("worksheet exists; judging is not overwritten")
                _write_json(path, build_worksheet(journal, ledgers, oracles))
                print(
                    f"wrote {path.relative_to(ROOT)}; fill caught_by, verdict, unsafe_fix"
                )
            elif args.command == "score":
                stored = (
                    _read_json(OUT / "runs.json")
                    if (OUT / "runs.json").exists()
                    else runs
                )
                report = score(
                    journal, _read_json(OUT / "worksheet.json"), ledgers, stored
                )
                _write_json(OUT / "report.json", report)
                print(json.dumps(report["summary"], indent=2))
    except PlanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
