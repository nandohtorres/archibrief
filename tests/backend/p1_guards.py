"""Regression guards for the P1 accuracy work (plan Step 0).

Two kinds of guard, both free to run:

* Offline replay of the deterministic stages (parse -> Trivy -> rules ->
  resource summary) on the P1 corpus. For every oracle issue it records which
  rule is expected to catch it and which fact the model input must carry. A
  fix to one stage cannot silently drop what another stage provides.
* Recorded reviews: the five baseline model outputs, reduced and frozen, with
  my judgement of what each caught. Detectors for the known false claims and
  unsafe fixes run on any report, and `assert_issues_preserved` is the
  invariant any later merge, de-duplication or noise cut must satisfy.

The held-out T3b case is deliberately absent. Add it only after the baseline
and any tuning are finished.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "p1_guards"
RECORDED = FIXTURES / "recorded"


@dataclass(frozen=True)
class Fact:
    """A value the model input must carry for an oracle issue."""

    type: str
    name: str
    setting: str
    value: object


@dataclass(frozen=True)
class Issue:
    """What must hold, stage by stage, for one oracle issue."""

    severity: str
    # Deterministic rule expected to catch it: (concern, resource name), or
    # None when only the model can (or no rule exists yet).
    rule: tuple[str, str] | None
    facts: tuple[Fact, ...]
    # How a finding counts as covering the issue: the resource is named and
    # one of these words appears.
    resource: str
    keywords: str


def _i(severity, rule, facts, resource, keywords) -> Issue:
    return Issue(severity, rule, tuple(facts), resource, keywords)


_URL_KW = r"unauthenticated|authorization[_ ]type\W*(?:=|is|of)?\W*NONE|no authentication"

T1_ISSUES: dict[str, Issue] = {
    "T1-01": _i(
        "High",
        ("sg_admin_ingress", "maintenance"),
        [],
        "maintenance",
        r"ssh|rdp|22|3389|0\.0\.0\.0/0|anywhere",
    ),
    "T1-02": _i(
        "High",
        None,
        [Fact("aws_route_table", "app", "route[0].cidr_block", "0.0.0.0/0")],
        r"app(?:_a)?",
        r"route|internet gateway|igw|public",
    ),
    "T1-03": _i(
        "Critical",
        ("iam_wildcard", "maintenance"),
        [],
        "maintenance",
        r"\*|wildcard|administrator|full admin",
    ),
    "T1-04": _i(
        "High", ("ec2_imdsv2", "maintenance"), [], "maintenance", r"imds|metadata|http_tokens"
    ),
    "T1-05": _i(
        "High",
        None,
        [
            Fact("aws_lambda_function_url", "contractor_export", "authorization_type", "NONE"),
            Fact(
                "aws_lambda_function_url",
                "contractor_export",
                "public_invocation_permissions",
                "both_actions_declared",
            ),
        ],
        "contractor_export",
        _URL_KW,
    ),
}

T2_ISSUES: dict[str, Issue] = {
    "T2-01": _i(
        "High",
        ("rds_backup_retention", "records"),
        [Fact("aws_db_instance", "records", "backup_retention_period", 0)],
        "records",
        r"backup",
    ),
    "T2-02": _i(
        "High",
        ("rds_multi_az", "records"),
        [Fact("aws_db_instance", "records", "multi_az", False)],
        "records",
        r"multi[_ -]?az|standby",
    ),
    "T2-03": _i(
        "High",
        ("dynamodb_pitr", "journal"),
        [Fact("aws_dynamodb_table", "journal", "point_in_time_recovery.enabled", False)],
        "journal",
        r"point[- ]in[- ]time|pitr",
    ),
    "T2-04": _i(
        "High",
        ("s3_versioning", "evidence"),
        [
            Fact(
                "aws_s3_bucket_versioning",
                "evidence",
                "versioning_configuration.status",
                "Suspended",
            )
        ],
        "evidence",
        r"versioning",
    ),
    "T2-05": _i(
        "High",
        None,
        [Fact("aws_s3_bucket_lifecycle_configuration", "evidence", "rule[0].expiration.days", 1)],
        "evidence",
        r"lifecycle|expire",
    ),
    "T2-06": _i(
        "Medium",
        ("sqs_dlq_retention", "ingest_failed"),
        [Fact("aws_sqs_queue", "ingest_failed", "message_retention_seconds", 60)],
        "ingest_failed",
        r"retain|retention|dead-letter|keeps messages",
    ),
    "T2-07": _i(
        "Low",
        None,
        [Fact("aws_cloudwatch_log_group", "debug", "retention_in_days", 0)],
        "debug",
        r"retention|never expires|indefinitely",
    ),
    "T2-08": _i(
        "Medium",
        None,
        [Fact("aws_ebs_volume", "scratch", "type", "io2")],
        "scratch",
        r"io2|volume|provisioned|attached|retired",
    ),
}

T3A_ISSUES: dict[str, Issue] = {
    "T3A-SEC-01": T1_ISSUES["T1-01"],
    "T3A-SEC-02": T1_ISSUES["T1-02"],
    "T3A-SEC-03": T1_ISSUES["T1-03"],
    "T3A-SEC-04": T1_ISSUES["T1-04"],
    "T3A-SEC-05": _i(
        "High",
        None,
        [
            Fact("aws_lambda_function_url", "dispatch", "authorization_type", "NONE"),
            Fact(
                "aws_lambda_function_url",
                "dispatch",
                "public_invocation_permissions",
                "both_actions_declared",
            ),
        ],
        "dispatch",
        _URL_KW,
    ),
    "T3A-DATA-01": T2_ISSUES["T2-01"],
    "T3A-DATA-02": T2_ISSUES["T2-02"],
    "T3A-DATA-03": T2_ISSUES["T2-03"],
    "T3A-DATA-05": T2_ISSUES["T2-05"],
    "T3A-DATA-06": T2_ISSUES["T2-06"],
    "T3A-DATA-07": T2_ISSUES["T2-07"],
    "T3A-DATA-08": T2_ISSUES["T2-08"],
    "T3A-ENTRY-01": _i(
        "High",
        None,
        [Fact("aws_apigatewayv2_route", "override", "authorization_type", "NONE")],
        "override",
        r"authorization|unauthenticated|NONE",
    ),
    "T3A-REGION-01": _i(
        "High",
        None,
        [Fact("aws_s3_bucket", "evidence", "provider.region", "us-east-2")],
        "evidence",
        r"us-east-2|\beu\b|region|ohio",
    ),
}

CASE_ISSUES: dict[str, dict[str, Issue]] = {
    "T1-small": T1_ISSUES,
    "T1-full": T1_ISSUES,
    "T2-small": T2_ISSUES,
    "T2-full": T2_ISSUES,
    "T3a": T3A_ISSUES,
}
MUST_FIND = ("Critical", "High")

# My judgement of the five recorded reviews (2026-11-14): oracle issues each
# review covered. Everything else was missed. Must-find: 29 of 31.
_ALL = lambda issues: set(issues)
JUDGED_CAUGHT: dict[int, set[str]] = {
    1: {"T1-01", "T1-02", "T1-03", "T1-04"},
    2: {"T1-01", "T1-02", "T1-03", "T1-04"},
    3: _ALL(T2_ISSUES),
    4: _ALL(T2_ISSUES) - {"T2-08"},
    5: _ALL(T3A_ISSUES),
}


# ----------------------------------------------------------- offline replay


@dataclass
class Replay:
    rules: list[dict]
    summary: dict
    parsed: dict
    scanner: dict | None = field(default=None)

    def entry(self, resource_type: str, name: str) -> dict | None:
        return next(
            (
                e
                for e in self.summary["resources"]
                if e["type"] == resource_type and e["name"] == name
            ),
            None,
        )

    def fact(self, resource_type: str, name: str, setting: str) -> object:
        """A setting or observed fact of a summary entry, as the model sees it."""
        entry = self.entry(resource_type, name)
        if entry is None:
            return "<not in summary>"
        for observed in (entry.get("observations") or {}).get("facts", []):
            if observed["setting"] == setting:
                return observed["value"]
        return (entry.get("settings") or {}).get(setting, "<absent>")

    def rule_catches(self, concern: str, name: str) -> bool:
        pattern = re.compile(rf"(?<![A-Za-z0-9_-]){re.escape(name)}(?![A-Za-z0-9_-])")
        return any(
            f.get("concern") == concern and pattern.search(f["finding"] + " " + f["evidence"])
            for f in self.rules
        )


def replay_case(case: dict, corpus: Path, trivy: str | None) -> Replay:
    """The deterministic stages on a corpus case, as production runs them:
    extract, parse with the archive root, Trivy on its own extraction."""
    from backend.lambdas.ingest.handler import parse_terraform_files
    from backend.lambdas.rule_engine.handler import run_rules
    from backend.lambdas.rule_engine.resource_summary import build_resource_summary
    from backend.lambdas.scan.handler import scan_files
    from backend.shared.archive import extract_archive
    from scripts.small_workload_eval import build_archive

    work = Path(tempfile.mkdtemp(prefix="p1guard-"))
    try:
        archive = build_archive(corpus, case, work / "case.tar.gz")
        extracted = work / "extracted"
        files = extract_archive(str(archive), str(extracted))
        parsed = asdict(parse_terraform_files(sorted(files), archive_root=str(extracted)))
        scanner = None
        if trivy:
            scan_dir = work / "scan"
            scan_list = extract_archive(str(archive), str(scan_dir))
            scanner = scan_files(str(scan_dir), sorted(scan_list), trivy)
        rules = [f.model_dump(mode="json") for f in run_rules(parsed, "p1-guard", scanner=scanner)]
        return Replay(rules, build_resource_summary(parsed), parsed, scanner)
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------- recorded reviews


def load_recorded(slot: int) -> dict:
    return json.loads((RECORDED / f"slot{slot}.json").read_text(encoding="utf-8"))


def _text(finding: dict) -> str:
    return " ".join(
        str(finding.get(k) or "") for k in ("finding", "evidence", "risk_impact", "recommendation")
    )


def covers(finding: dict, issue: Issue) -> bool:
    """The finding names the issue's resource and describes its defect."""
    text = _text(finding)
    named = re.search(rf"(?<![A-Za-z0-9_-]){issue.resource}(?![A-Za-z0-9_-])", text)
    return bool(named and re.search(issue.keywords, text, re.IGNORECASE))


def covered_issues(findings: list[dict], issues: dict[str, Issue]) -> set[str]:
    return {i for i, issue in issues.items() if any(covers(f, issue) for f in findings)}


def assert_issues_preserved(
    before: list[dict], after: list[dict], issues: dict[str, Issue]
) -> None:
    """The invariant for any merge, de-duplication or noise cut: no oracle
    issue covered before may be uncovered after."""
    lost = covered_issues(before, issues) - covered_issues(after, issues)
    assert not lost, f"issues no longer covered after the change: {sorted(lost)}"


# Known defects, as detectors usable on any report. Each returns the findings
# that trip it. The recorded baseline trips each once or twice; a fixed system
# must trip none (see `violations`).
_FALSE_LIFECYCLE = re.compile(
    r"filter_scope|restricted_or_unknown|may apply only to a subset", re.IGNORECASE
)
_URL_VPC_FIX = re.compile(r"\bvpc\b", re.IGNORECASE)
_REMOVES_RETENTION = re.compile(
    r"(?:expiration\.days\s+should\s+be\s+removed|remov\w+\s+(?:the\s+)?(?:expiration|lifecycle))",
    re.IGNORECASE,
)


def false_lifecycle_scope(findings: list[dict]) -> list[dict]:
    return [f for f in findings if _FALSE_LIFECYCLE.search(_text(f))]


def ineffective_url_fix(findings: list[dict]) -> list[dict]:
    """A function-URL finding whose fix is a VPC change: a VPC does not
    restrict a function URL and can break outbound access."""
    return [
        f
        for f in findings
        if re.search(r"function url", _text(f), re.IGNORECASE)
        and _URL_VPC_FIX.search(str(f.get("recommendation") or ""))
    ]


def retention_removal_fix(findings: list[dict]) -> list[dict]:
    """A fix that removes an expiry rule; unsafe when the brief requires that
    retention window."""
    return [f for f in findings if _REMOVES_RETENTION.search(str(f.get("recommendation") or ""))]


DETECTORS = {
    "false_lifecycle_scope": false_lifecycle_scope,
    "ineffective_url_fix": ineffective_url_fix,
    "retention_removal_fix": retention_removal_fix,
}


def violations(findings: list[dict]) -> dict[str, list[str]]:
    """Finding ids tripping each detector; an empty dict is a clean report."""
    found = {
        name: [f["finding_id"] for f in detect(findings)] for name, detect in DETECTORS.items()
    }
    return {name: ids for name, ids in found.items() if ids}
