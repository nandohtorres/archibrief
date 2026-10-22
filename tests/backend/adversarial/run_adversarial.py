"""Runs every frozen answer-key check in both modes and writes:

- results/results.json        raw verdict per (check, mode), with observations
- results/results_table.md    the same as a table, plus metrics
- model_eval/inputs/<case>.json  reasoning-model inputs for a later paid run
                                 (status NOT RUN; nothing here calls a model)

Usage, from the repository root, with the existing backend venv:
    TRIVY_PATH=<trivy binary> python -m tests.backend.adversarial.run_adversarial

Raw verdicts are never edited. ADJUDICATION adds a reviewer note to a verdict
that is right for the wrong reason or wrong because of the probe, and the
metrics are reported both raw and adjudicated.
"""

from __future__ import annotations

import json
import tempfile
from collections import Counter
from pathlib import Path

from tests.backend.adversarial.harness import (
    HERE,
    judge,
    load_answer_key,
    probe,
    run_fixture,
    trivy_path,
)

RESULTS = HERE / "results"
MODEL_INPUTS = HERE / "model_eval" / "inputs"

# Which frozen checks measure which property. Recorded here, after the
# freeze, because the answer key groups by kind and scope only.
ATTRIBUTION = {"F02-D-15", "F03-D-02", "F03-D-06", "F04-D-04", "F04-D-05", "F09-D-05"}

# verdict -> (adjudicated verdict, note). Applied identically in both modes.
ADJUDICATION: dict[str, tuple[str, str]] = {
    "F02-D-15": (
        "pass",
        (
            "Probe artifact: 'role' matched the rule's generic recommendation text "
            "('...the role actually needs'), not a claim that the policy is attached."
        ),
    ),
    "F02-D-05": (
        "pass (wrong reason)",
        (
            "Not flagged only because a policy document's principals type \"*\" isn't "
            "recognised as public at all (post-freeze probe 1); the dropped Condition "
            "never mattered."
        ),
    ),
    "F03-D-04": (
        "pass (vacuous)",
        "Every IMDS finding is suppressed by the account default (B2).",
    ),
    "F03-D-05": (
        "pass (vacuous)",
        "Every IMDS finding is suppressed by the account default (B2).",
    ),
    "F03-D-06": (
        "pass (vacuous)",
        "Every IMDS finding is suppressed by the account default (B2).",
    ),
    "F06-D-03": (
        "fail",
        (
            "Probe weaker than intent: the selection appears in the summary with empty "
            "settings, so which resources it protects is still invisible."
        ),
    ),
    "F06-I-01": (
        "fail",
        "Same as F06-D-03: entry present, nothing about what it selects.",
    ),
    "F08-D-01": (
        "fail",
        (
            "Probe weaker than intent: the lifecycle configuration appears with empty "
            "settings; no expiration or noncurrent-version data reaches the model."
        ),
    ),
    "F08-I-01": ("fail", "Same as F08-D-01."),
}


def category(check: dict) -> str:
    if check["id"] in ATTRIBUTION:
        return "attribution"
    if check["scope"] == "coverage_gap":
        return "coverage_gap"
    if check["kind"] == "acceptable_uncertainty":
        return "acceptable"
    if check["scope"] == "rule_covered" and check["kind"] == "must_detect":
        return "recall"
    if check["scope"] == "rule_covered" and check["kind"] == "must_not_claim":
        return "false_claim"
    if check["kind"] == "must_disclose" or check["id"] in {"F01-D-08", "F04-D-06"}:
        return "uncertainty"
    return "evidence_handling"


def main() -> None:
    key = load_answer_key()
    modes = ["rules"] + (["trivy"] if trivy_path() else [])
    cache: dict[tuple[str, str], object] = {}
    work_root = Path(tempfile.mkdtemp(prefix="archibrief-adversarial-"))

    def get(fixture: str, mode: str):
        if (fixture, mode) not in cache:
            cache[(fixture, mode)] = run_fixture(
                fixture, mode, work_root / f"{fixture.replace('/', '_')}_{mode}"
            )
        return cache[(fixture, mode)]

    rows = []
    for case in key["cases"]:
        for check in case["checks"]:
            for mode in modes:
                run = get(case["fixture"], mode)
                ctx = {
                    "fixture": case["fixture"],
                    "work": work_root / f"{check['id']}_{mode}",
                    "run_other": get,
                }
                ctx["work"].mkdir(parents=True, exist_ok=True)
                matched, observed = probe(check["probe"], run, ctx)
                raw = judge(check["kind"], matched)
                adjudicated, note = ADJUDICATION.get(check["id"], (raw, ""))
                rows.append(
                    {
                        "case": case["id"],
                        "check": check["id"],
                        "mode": mode,
                        "kind": check["kind"],
                        "scope": check["scope"],
                        "category": category(check),
                        "resource": check["resource"],
                        "expected": check["what"],
                        "evidence": check["evidence"],
                        "observed": observed,
                        "verdict": raw,
                        "adjudicated": adjudicated,
                        "note": note,
                    }
                )

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "results.json").write_text(
        json.dumps(rows, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    _write_table(rows, modes)
    _write_model_inputs(key, get)
    print(f"{len(rows)} verdicts written to {RESULTS}")


def _rate(rows: list[dict], cat: str, mode: str, field: str) -> str:
    picked = [r for r in rows if r["category"] == cat and r["mode"] == mode]
    if not picked:
        return "n/a"
    passed = sum(1 for r in picked if r[field].startswith("pass"))
    return f"{passed}/{len(picked)}"


def _write_table(rows: list[dict], modes: list[str]) -> None:
    lines = ["# Adversarial results (generated by run_adversarial.py)", ""]
    lines.append("## Metrics")
    lines.append("")
    lines.append(
        "Pass counts per category. Raw = the frozen probe's verdict; adjudicated = after the notes below."
    )
    lines.append("")
    lines.append(
        "| Category | " + " | ".join(f"{m} raw | {m} adjudicated" for m in modes) + " |"
    )
    lines.append("|---|" + "---|---|" * len(modes))
    for cat, label in [
        ("recall", "Recall: rule-covered defects detected"),
        ("false_claim", "False claims avoided (rule-covered must-not-claim)"),
        ("attribution", "Attribution correct"),
        ("uncertainty", "Uncertainty / gaps disclosed"),
        ("evidence_handling", "Other evidence handling"),
        ("coverage_gap", "Coverage-gap expectations met"),
        ("acceptable", "Acceptable-either-way (recorded only)"),
    ]:
        cells = " | ".join(
            f"{_rate(rows, cat, m, 'verdict')} | {_rate(rows, cat, m, 'adjudicated')}"
            for m in modes
        )
        lines.append(f"| {label} | {cells} |")
    lines.append("")
    lines.append(
        "Citation provenance and semantic support: **not measured**. Deterministic findings carry no citations, and no model ran."
    )
    lines.append("")
    counts = Counter((r["mode"], r["verdict"].split(" ")[0]) for r in rows)
    lines.append(
        "Totals: "
        + "; ".join(
            f"{m}: {counts[(m, 'pass')]} pass, {counts[(m, 'fail')]} fail"
            for m in modes
        )
    )
    lines.append("")
    lines.append("## Per check and mode")
    lines.append("")
    lines.append(
        "| Check | Mode | Kind / scope | Resource | Expected | Observed | Verdict | Adjudicated |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        obs = r["observed"].replace("|", "/").replace("\n", " ")[:180]
        exp = r["expected"].replace("|", "/")[:160]
        adj = r["adjudicated"] + (f" ({r['note']})" if r["note"] else "")
        lines.append(
            f"| {r['check']} | {r['mode']} | {r['kind']} / {r['scope']} | {r['resource']} | {exp} | {obs} | {r['verdict']} | {adj.replace('|', '/')} |"
        )
    (RESULTS / "results_table.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )


def _write_model_inputs(key: dict, get) -> None:
    """What the reasoning node would receive (rules-only mode), for a later
    paid evaluation. Scoring criteria live in model_eval/SCORING.md."""
    MODEL_INPUTS.mkdir(parents=True, exist_ok=True)
    for case in key["cases"]:
        run = get(case["fixture"], "rules")
        payload = {
            "status": "NOT RUN — prepared input only; no model was called",
            "case": case["id"],
            "family": case["family"],
            "variant": case["variant"],
            "workload_brief": case["brief"],
            "rule_findings": [
                {
                    k: f[k]
                    for k in (
                        "finding_id",
                        "category",
                        "type",
                        "finding",
                        "evidence",
                        "risk_impact",
                        "recommendation",
                        "concern",
                    )
                }
                for f in run.findings
            ],
            "terraform_resources": run.summary,
            "scoring": "model_eval/SCORING.md#" + case["family"],
        }
        (MODEL_INPUTS / f"{case['id']}.json").write_text(
            json.dumps(payload, indent=1) + "\n", encoding="utf-8", newline="\n"
        )


if __name__ == "__main__":
    main()
