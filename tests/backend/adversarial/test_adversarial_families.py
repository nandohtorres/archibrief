"""Adversarial families 1-9 against the frozen answer key (answer_key.json).

One test per (check, mode). Modes:
- rules: ArchiBrief's own rules only (Trivy unavailable).
- trivy: offline Trivy (--skip-check-update, the scanner's isolated
  environment) plus the rules. Skipped when no Trivy binary is found.

A failing test is a defect or a documented coverage gap (see the check's
scope); none is marked xfail. Deselect gaps with `-m "not coverage_gap"`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.backend.adversarial.harness import (
    Run,
    judge,
    load_answer_key,
    probe,
    run_fixture,
    trivy_path,
)
from tests.backend.adversarial.probe_errata import CHECKS, corrected_probe

KEY = load_answer_key()
TRIVY = trivy_path()
MODES = ["rules", "trivy"]

_RUNS: dict[tuple[str, str], Run] = {}


@pytest.fixture(scope="session")
def runs(tmp_path_factory: pytest.TempPathFactory):
    def get(fixture: str, mode: str) -> Run:
        if (fixture, mode) not in _RUNS:
            work = tmp_path_factory.mktemp(fixture.replace("/", "_") + "_" + mode)
            _RUNS[(fixture, mode)] = run_fixture(fixture, mode, work)
        return _RUNS[(fixture, mode)]

    return get


def _params():
    for case in KEY["cases"]:
        for check in case["checks"]:
            for mode in MODES:
                marks = []
                if mode == "trivy" and TRIVY is None:
                    marks.append(
                        pytest.mark.skip(reason="Trivy not installed (set TRIVY_PATH)")
                    )
                if check["scope"] == "coverage_gap":
                    marks.append(pytest.mark.coverage_gap)
                yield pytest.param(
                    case, check, mode, id=f"{check['id']}-{mode}", marks=marks
                )


@pytest.mark.parametrize(("case", "check", "mode"), list(_params()))
def test_check(case: dict, check: dict, mode: str, runs, tmp_path: Path) -> None:
    run = runs(case["fixture"], mode)
    if mode == "trivy":
        assert run.scanner and run.scanner["status"] == "ok", run.scanner
    matched, observed = probe(
        check["probe"],
        run,
        {"fixture": case["fixture"], "work": tmp_path, "run_other": runs},
    )
    verdict = judge(check["kind"], matched)
    if not verdict.startswith("pass") and check["id"] in CHECKS:
        corrected, reason = corrected_probe(check["id"], run)
        assert corrected, (
            f"Raw frozen verdict: {verdict}; supplemental contract failed: {reason}"
        )
        return
    assert verdict.startswith("pass"), (
        f"{check['id']} [{check['kind']}, {check['scope']}] {check['what']}\n"
        f"resource: {check['resource']}\nevidence: {check['evidence']}\nobserved: {observed}"
    )
