"""Reasoning-quality evaluation set for reason_node — a genuinely different
question from what validate_reason_node.py checks.

validate_reason_node.py (and reason_node's own server-side verification,
see backend/agent/nodes/reason.py) proves TRUSTWORTHINESS: is a returned
citation real (the chunk_id was actually retrieved, the quote actually
appears in that chunk's text)? It says nothing about QUALITY: did the
model find the issues a competent human reviewer would expect from a given
workload brief, did it invent anything, and is a technically-real citation
actually good support for the claim it's attached to (a citation can be
real and still not fully support the finding's prose).

Mirrors backend/corpus/eval.py's dev-set/held-out-set convention (see that
file's module docstring for why two sets exist) and its scoring-precision
discipline (name exactly what's measured, don't overclaim). Key
differences from the retrieval eval, each deliberate:

- Ground truth here is EXPECTED FINDING TOPICS, not expected chunk_ids.
  A workload brief's "correct answer" for reasoning is a set of ISSUES a
  reviewer should raise, not a specific retrieved passage — the same real
  issue can be legitimately supported by more than one WAF/FSBP/CIS
  passage, and matching a specific citation exactly would penalize a
  model for citing an equally-valid alternative source.
- Matching is keyword-based against the FINDING'S OWN TEXT (finding +
  evidence + risk_impact), not against corpus chunk content — this
  project's established structural-test pattern (see
  tests/backend/corpus/test_eval.py's _QUERY_KEYWORDS convention) applied
  to a different artifact. Deliberately NOT an LLM-judge: grading the
  model's output with another model call adds real cost, a second unverified
  trust boundary, and meta-eval circularity (the same failure modes this
  project is trying to catch in the judged model could just as easily
  affect the judge). Keyword matching is coarser but cheap, deterministic,
  and auditable by reading this file — matching the same tradeoff
  eval.py's own docstring already accepts for retrieval scoring.
- Only RECALL (did an expected topic get covered) is scored as a hard
  number. PRECISION deliberately is not, and this is a real, named
  limitation, not an oversight: a "wrong" or "extra" finding can only be
  judged against an EXHAUSTIVE list of every valid finding a workload
  brief could produce, and hand-labeling that exhaustively for open-ended
  reasoning output isn't realistic the way "the answer is these 1-3
  specific chunks" is for retrieval. Instead, any real (non-rule-engine)
  finding that doesn't match an expected topic is surfaced in the report
  as "unmatched" for a human to read and judge — genuinely extra insight,
  or a real problem — rather than auto-scored as a false positive.
- A CITATION-RELEVANCE check is included as a partial, explicit mitigation
  for the citation-shaped-hallucination residual risk: each expected topic
  names the document_id(s) that would plausibly support it. If a matched
  finding's (already server-verified-real) citation comes from a document
  outside that plausible set, it's flagged for human review — not treated
  as an automatic failure, since a model citing a different-but-still-
  valid source is legitimate, just worth a second look.

Further design details:
- Pure substring matching can't tell "root MFA is not configured" from
  "root MFA is enabled" apart, since both contain "root"+"mfa". Each topic
  has an explicit, auditable `negative_phrases` list (not a generic NLP
  negation heuristic), and `not-observable` findings never count as
  coverage: an "X cannot be verified" finding should not satisfy a topic
  requiring X to be a confirmed problem.
- Negative phrases use "already" as a disambiguating marker (e.g. "mfa is
  already enabled", not "mfa is enabled"). Without it, a phrase like "mfa
  configured" is a substring of the real-gap text "no MFA configured" and
  would wrongly zero the recall of correct findings; "no X is Y" keeps "is
  Y" contiguous, so any "X is Y" phrase collides with its own negation.
  The offline test suite covers this.
- Citation relevance is a 3-way state, `"plausible" | "implausible" |
  "missing" | None`, so "no citation present" isn't reported as "citation
  from an unexpected document".
- `topic_hits`/`unmatched_findings` keep the full `Finding.model_dump()`
  so a human reviewing the JSON report can verify a match and read the
  evidence and citation.
- Each brief's retrieval_query must cover all of its expected topics;
  otherwise a miss measures a retrieval gap, not a reasoning gap. Queries
  were checked by reasoning, not empirically against real embeddings.
- Ground-truth descriptions claim only what the brief establishes. For
  example, CloudTrail Event History provides a default 90-day
  management-event lookback even with zero trails configured, so the
  no-cloudtrail topic is about persistent logging and S3 data events, not
  "no audit log at all". IAM groups cannot be principals in a
  resource-based policy, so h01 uses an identity-based policy attached to
  the group.

PRECISION note: precision is not auto-scored (unmatched findings are
surfaced, never penalized), but manually labeling a handful of briefs'
findings is tractable. `precision_label` fields are provisioned throughout
so a human can fill them in ("supported"/"unsupported"/"unclear") after a
real run.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from backend.shared.models.finding import Finding, FindingType


class ExpectedFinding(BaseModel):
    """One issue a competent reviewer should raise for a given workload
    brief, described loosely enough to match a range of correct phrasings
    (a hand-typed "keyword group") rather than one exact sentence."""

    topic_id: str
    category: str  # FindingCategory value, informational only — not score-gating
    description: str  # human-readable, for report output only
    # Each inner list is a synonym/phrasing group; ALL groups must have at
    # least one match (AND across groups, OR within a group) for a Finding
    # to count as covering this topic. Keeps matching structured — not a
    # single loose keyword, not a brittle exact phrase.
    keyword_groups: list[list[str]]
    # Phrases indicating the OPPOSITE state (the control is already in
    # place) — if any appears in the finding's text, it does NOT count as
    # coverage even when keyword_groups otherwise match. Explicit and
    # hand-audited per topic rather than a generic negation heuristic;
    # deliberately short/conservative lists, not exhaustive synonym
    # coverage (see module docstring).
    negative_phrases: list[str] = Field(default_factory=list)
    # document_id(s) a citation for this topic would plausibly come from —
    # used only for the soft citation-relevance flag, never to reject a
    # match outright.
    plausible_source_documents: list[str]


class ReasoningEvalBrief(BaseModel):
    """One workload brief plus its full reason_node input (mirrors
    validate_reason_node.py's _WORKLOAD_BRIEF/_RETRIEVAL_QUERY/_RULE_FINDINGS
    shape exactly, so this eval exercises the real interface) and its
    expected NEW findings — topics the MODEL should surface, deliberately
    excluding anything already covered by rule_findings (reason_node's
    SYSTEM_PROMPT explicitly forbids the model from restating those, and
    resolve_rule_findings() attaches them server-side regardless of what
    the model returns — scoring the model against them would test the
    wrong thing)."""

    brief_id: str
    workload_brief: str
    retrieval_query: str
    rule_findings: list[dict] = Field(default_factory=list)
    # RuleEngine's resource summary as Reason receives it (ADR-0049).
    terraform_resources: dict | None = None
    expected_findings: list[ExpectedFinding]
    notes: str | None = None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()


def _finding_covers_topic(finding: Finding, expected: ExpectedFinding) -> bool:
    # A "the status of X cannot be verified" finding must never satisfy a
    # topic that requires X to be a confirmed problem.
    if finding.type == FindingType.NOT_OBSERVABLE:
        return False
    haystack = _normalize(f"{finding.finding} {finding.evidence} {finding.risk_impact}")
    for group in expected.keyword_groups:
        if not any(keyword.lower() in haystack for keyword in group):
            return False
    return not any(phrase.lower() in haystack for phrase in expected.negative_phrases)


def _finding_with_label(finding: Finding) -> dict:
    """Full finding payload + a slot for manual precision labeling after a
    real run (see module docstring's PRECISION note) — never auto-filled
    here, this eval doesn't judge precision itself."""
    return {"finding": finding.model_dump(mode="json"), "precision_label": None}


def score_reasoning(
    findings: list[Finding],
    brief: ReasoningEvalBrief,
) -> dict:
    """Scores one brief's actual model-produced findings (NOT including the
    server-attached rule_findings — pass only what parse_model_findings()
    returned, matching what expected_findings was authored against) against
    its expected_findings.

    Returns per-topic coverage (the full covering finding(s), if any, and
    whether their citations' document_id(s) were in the topic's
    plausible_source_documents — see citation_relevance below), plus a
    list of findings that matched no expected topic at all (see module
    docstring: reported for human review, never auto-scored as wrong)."""
    topic_hits: list[dict] = []
    matched_finding_ids: set[str] = set()

    for expected in brief.expected_findings:
        covering = [f for f in findings if _finding_covers_topic(f, expected)]
        if covering:
            matched_finding_ids.update(f.finding_id for f in covering)
            cited = [f for f in covering if f.citation is not None]
            if not cited:
                # Distinct from "wrong document": no citation exists to judge at all.
                citation_relevance = "missing"
            elif any(f.citation.document_id in expected.plausible_source_documents for f in cited):
                citation_relevance = "plausible"
            else:
                citation_relevance = "implausible"
        else:
            citation_relevance = None  # not applicable — nothing matched
        topic_hits.append(
            {
                "topic_id": expected.topic_id,
                "description": expected.description,
                "covered": bool(covering),
                "covered_by_findings": [_finding_with_label(f) for f in covering],
                "citation_relevance": citation_relevance,
            }
        )

    unmatched_findings = [
        _finding_with_label(f) for f in findings if f.finding_id not in matched_finding_ids
    ]

    total = len(brief.expected_findings)
    covered = sum(1 for hit in topic_hits if hit["covered"])
    return {
        "brief_id": brief.brief_id,
        "topic_recall": covered / total if total else 0.0,
        "topics_covered": covered,
        "topics_total": total,
        "topic_hits": topic_hits,
        "unmatched_findings": unmatched_findings,
    }


# --- Dev set -----------------------------------------------------------

EVAL_BRIEFS: list[ReasoningEvalBrief] = [
    ReasoningEvalBrief(
        brief_id="r01",
        workload_brief=(
            "We run a single S3 bucket ('customer-records-prod') that stores critical "
            "customer PII and billing records for a small SaaS product. The bucket has "
            "no versioning enabled, and the AWS account's root user does not have MFA "
            "configured. There is no CloudTrail trail in the account. The application "
            "backend is a single Lambda function reading/writing directly to this bucket."
        ),
        # Covers all three expected topics, so a miss measures reasoning, not
        # retrieval.
        retrieval_query=(
            "S3 bucket versioning for data recovery, AWS account root user MFA best "
            "practices, CloudTrail logging for API and data-access auditing, and "
            "least-privilege IAM permission scoping for a Lambda function with direct "
            "S3 access"
        ),
        rule_findings=[
            {
                "finding_id": "00000000-0000-0000-0000-000000000001",
                "review_id": "r01",
                "category": "recovery",
                "type": "deterministic-rule-result",
                "finding": "S3 bucket 'customer-records-prod' does not have versioning enabled",
                "evidence": (
                    'resource "aws_s3_bucket" "customer-records-prod" found with no '
                    "enabled versioning configuration"
                ),
                "citation": None,
                "confidence": 1.0,
                "confidence_inputs": {
                    "evidence_directness": 1.0,
                    "source_agreement": 1.0,
                    "rule_determinism": 1.0,
                },
                "risk_impact": "Accidental or malicious object deletion/overwrite cannot be recovered.",
                "recommendation": 'Enable aws_s3_bucket_versioning with status = "Enabled".',
                "framework_mapping": ["AWS Well-Architected: Reliability Pillar"],
                "alternatives_considered": [],
                "depth_level": "lightweight",
                "deterministic_rule_version": "rule_engine@2026-09-08",
            }
        ],
        expected_findings=[
            ExpectedFinding(
                topic_id="root-mfa",
                category="iam",
                description="Root user has no MFA configured — a critical account-level exposure.",
                keyword_groups=[["root"], ["mfa", "multi-factor"]],
                negative_phrases=[
                    "mfa is already enabled",
                    "already has mfa configured",
                    "mfa is already configured",
                    "mfa is already enforced",
                ],
                plausible_source_documents=[
                    "waf-security-pillar",
                    "iam-best-practices",
                    "aws-cis-foundations-mapping",
                    "aws-fsbp-standard",
                ],
            ),
            ExpectedFinding(
                topic_id="no-cloudtrail",
                category="observability",
                # CloudTrail Event History provides a default 90-day management-event
                # lookback even with zero trails configured. The real gap is
                # persistent/long-term logging plus S3 object-level (data event)
                # logging, which a trail is required for.
                description=(
                    "No CloudTrail trail is configured — beyond the default 90-day "
                    "management-event history, there's no persistent audit log and no "
                    "S3 object-level (data event) logging for PII access."
                ),
                keyword_groups=[["cloudtrail"], ["log", "audit", "logging", "trail"]],
                negative_phrases=[
                    "cloudtrail is already enabled",
                    "a trail already exists",
                    "trail is already configured",
                    "already has a trail",
                ],
                plausible_source_documents=[
                    "waf-security-pillar",
                    "aws-cis-foundations-mapping",
                    "aws-fsbp-standard",
                    "aws-security-reference-architecture",
                ],
            ),
            ExpectedFinding(
                topic_id="lambda-broad-access",
                category="iam",
                # The brief never establishes broad permissions; it only omits any
                # mention of scoping. So this is an ASSUMPTION-type open question a
                # competent reviewer would raise, not an asserted defect.
                description=(
                    "The single Lambda's IAM permission scope is unstated — a competent "
                    "reviewer should flag this as an open question/assumption given no "
                    "least-privilege scoping is mentioned, not assert it's definitely broad."
                ),
                keyword_groups=[
                    ["lambda"],
                    ["least privilege", "least-privilege", "iam", "permission", "scop"],
                ],
                negative_phrases=[
                    "is tightly scoped",
                    "already follows least privilege",
                    "narrowly scoped",
                ],
                plausible_source_documents=["waf-security-pillar", "iam-best-practices"],
            ),
        ],
        notes=(
            "Uses the scripted validate_reason_node.py brief. Measures completeness across root MFA, absent CloudTrail and broad Lambda permissions, rather than accepting coverage of only one topic."
        ),
    ),
    ReasoningEvalBrief(
        brief_id="r02",
        workload_brief=(
            "Our platform team runs about 40 AWS accounts under one Organization with no "
            "assigned cost owner per account and no tagging policy — nobody is accountable "
            "for reviewing monthly spend. Several EC2 instances are sized at the largest "
            "available instance type 'just in case' with no monitoring of actual "
            "utilization, and Savings Plans / Reserved Instances are not used anywhere."
        ),
        # Mentions commitment discounts so no-commitment-discounts can get
        # relevant retrieved evidence.
        retrieval_query=(
            "establishing cost ownership and tagging policies across accounts, "
            "rightsizing EC2 instances based on utilization, and using Savings Plans "
            "or Reserved Instances for commitment-based discounts"
        ),
        expected_findings=[
            ExpectedFinding(
                topic_id="no-cost-ownership",
                category="cost",
                description="No cost owner or tagging policy — nobody accountable for spend.",
                keyword_groups=[["cost"], ["owner", "ownership", "accountab"]],
                negative_phrases=[
                    "already has a cost owner",
                    "tagging policy is already enforced",
                    "cost owner is already assigned",
                ],
                plausible_source_documents=["waf-cost-optimization-pillar"],
            ),
            ExpectedFinding(
                topic_id="oversized-instances",
                category="cost",
                description="EC2 instances oversized without utilization monitoring — rightsizing opportunity.",
                keyword_groups=[
                    ["rightsiz", "oversiz", "right-siz", "instance size", "utilization"]
                ],
                negative_phrases=["properly sized", "already rightsized", "correctly sized"],
                plausible_source_documents=[
                    "waf-cost-optimization-pillar",
                    "waf-performance-efficiency-pillar",
                ],
            ),
            ExpectedFinding(
                topic_id="no-commitment-discounts",
                category="cost",
                # The brief never establishes steady-state usage, so the description
                # doesn't claim it; it only says no Savings Plans/RIs are used.
                description="No Savings Plans/Reserved Instances used anywhere — worth evaluating for commitment-based discounts.",
                keyword_groups=[["savings plan", "reserved instance", "commitment"]],
                negative_phrases=[
                    "savings plans are already used",
                    "reserved instances are already used",
                    "already uses savings plans",
                ],
                plausible_source_documents=["waf-cost-optimization-pillar"],
            ),
        ],
    ),
    ReasoningEvalBrief(
        brief_id="r03",
        workload_brief=(
            "We operate a single production RDS PostgreSQL instance with automated backups "
            "disabled and Multi-AZ turned off, in a single Availability Zone. There's no "
            "documented disaster recovery plan, and the team has never actually tested a "
            "restore from backup."
        ),
        retrieval_query="RDS Multi-AZ and automated backups for disaster recovery testing",
        expected_findings=[
            ExpectedFinding(
                topic_id="no-multi-az",
                category="availability",
                description="Single-AZ RDS deployment with Multi-AZ disabled — availability risk.",
                keyword_groups=[["multi-az", "multi az", "availability zone"]],
                negative_phrases=[
                    "multi-az is already enabled",
                    "already multi-az",
                    "multi-az deployment is already configured",
                ],
                plausible_source_documents=["waf-reliability-pillar"],
            ),
            ExpectedFinding(
                topic_id="backups-disabled",
                category="recovery",
                description="Automated RDS backups are disabled — no point-in-time recovery.",
                # Guards against cross-topic bleed: "backup restore testing is
                # disabled" is about untested restores, not disabled backups.
                # negative_phrases alone doesn't fully solve this, but combined with
                # requiring "backup" AND a disabled-state word, a restore-testing
                # sentence is much less likely to match both groups.
                keyword_groups=[
                    ["backup"],
                    ["disabled", "not enabled", "no automated", "turned off"],
                ],
                negative_phrases=[
                    "backups are already enabled",
                    "automated backups are already configured",
                    "backup is already enabled",
                ],
                plausible_source_documents=["waf-reliability-pillar"],
            ),
            ExpectedFinding(
                topic_id="untested-restore",
                category="recovery",
                description="Restore from backup has never been tested — an unverified recovery path.",
                keyword_groups=[["restore", "recovery"], ["test", "tested", "untested", "verif"]],
                negative_phrases=[
                    "restore has already been tested",
                    "recovery has already been validated",
                    "already successfully tested",
                ],
                plausible_source_documents=["waf-reliability-pillar"],
            ),
        ],
    ),
]


# --- Held-out set --------------------------------------------------------
# Authored separately from EVAL_BRIEFS, same rationale as eval_holdout.py:
# a reasoning pipeline that happened to fit this project's own dev-set
# phrasing/topics shouldn't be trusted as generalizing without a genuinely
# separate check.

HOLDOUT_BRIEFS: list[ReasoningEvalBrief] = [
    ReasoningEvalBrief(
        brief_id="h01",
        # Uses an identity-based policy attached to the group: IAM groups
        # cannot be principals in a resource-based policy (a principal must be
        # an authenticated entity).
        workload_brief=(
            "Our data science team spins up EC2 instances for training jobs directly from "
            "personal IAM user access keys that don't expire, shared across the team via a "
            "spreadsheet. The training data lives in an S3 bucket, and an identity-based "
            "policy attached to the team's entire IAM group grants s3:* on that bucket."
        ),
        retrieval_query=(
            "long-term IAM access keys shared across a team, and a wildcard S3 bucket "
            "policy granting full access to an entire IAM group"
        ),
        expected_findings=[
            ExpectedFinding(
                topic_id="shared-long-term-keys",
                category="iam",
                description="Long-term IAM access keys shared across a team instead of temporary/federated credentials.",
                keyword_groups=[
                    ["access key", "long-term", "long term"],
                    ["shar", "federat", "temporary"],
                ],
                negative_phrases=[
                    "keys are already rotated regularly",
                    "temporary credentials are already used",
                    "federated access is already used",
                ],
                plausible_source_documents=["iam-best-practices", "waf-security-pillar"],
            ),
            ExpectedFinding(
                topic_id="wildcard-bucket-policy",
                category="exposure",
                description="An IAM group policy grants s3:* on the bucket — violates least privilege.",
                keyword_groups=[
                    ["s3:*", "wildcard", "all actions", "full access"],
                    ["least privilege", "least-privilege"],
                ],
                negative_phrases=[
                    "policy is already scoped",
                    "least privilege is already enforced",
                    "no wildcard permissions",
                ],
                plausible_source_documents=[
                    "waf-security-pillar",
                    "iam-best-practices",
                    "aws-fsbp-standard",
                ],
            ),
        ],
    ),
    ReasoningEvalBrief(
        brief_id="h02",
        workload_brief=(
            "A globally-distributed consumer app keeps every environment (dev, staging, "
            "prod) running 24/7 in a single AWS Region even though dev and staging see "
            "almost no traffic outside business hours, and none of the data-processing "
            "batch jobs use Spot Instances despite being fully fault-tolerant and "
            "restartable."
        ),
        retrieval_query="scheduling non-production environments and using Spot Instances for fault-tolerant workloads",
        expected_findings=[
            ExpectedFinding(
                topic_id="non-prod-always-on",
                category="cost",
                description="Dev/staging run 24/7 despite low off-hours usage — no scheduled shutdown.",
                keyword_groups=[
                    ["dev", "staging", "non-production", "non production"],
                    ["schedul", "shut down", "shutdown", "24/7"],
                ],
                negative_phrases=[
                    "already scheduled to shut down",
                    "auto-stop is already configured",
                    "already shuts down outside business hours",
                ],
                plausible_source_documents=[
                    "waf-cost-optimization-pillar",
                    "waf-sustainability-pillar",
                ],
            ),
            ExpectedFinding(
                topic_id="no-spot-for-fault-tolerant",
                category="cost",
                description="Fault-tolerant, restartable batch jobs don't use Spot Instances.",
                keyword_groups=[
                    ["spot instance", "spot"],
                    ["fault-toleran", "fault toleran", "restart"],
                ],
                negative_phrases=["already uses spot instances", "spot is already used for"],
                plausible_source_documents=[
                    "waf-cost-optimization-pillar",
                    "waf-performance-efficiency-pillar",
                ],
            ),
        ],
    ),
    ReasoningEvalBrief(
        brief_id="h03",
        workload_brief=(
            "Our sustainability report needs input on a workload where all compute runs in "
            "one Region chosen purely for lowest latency to a North American customer base, "
            "and the engineering team assumes AWS alone is responsible for the workload's "
            "carbon footprint since 'it's all in the cloud.'"
        ),
        retrieval_query="shared responsibility for sustainability of the cloud versus in the cloud",
        expected_findings=[
            ExpectedFinding(
                topic_id="shared-responsibility-misunderstanding",
                category="observability",
                description=(
                    "Team assumes AWS alone owns sustainability impact — misunderstands the "
                    "shared responsibility split between 'of the cloud' and 'in the cloud'."
                ),
                # Doesn't require the exact phrase "shared responsibility": a correct
                # explanation of the AWS/customer split can use different wording.
                keyword_groups=[
                    ["shared responsibility", "responsibility model", "shared-responsibility"],
                    ["sustainab", "carbon", "of the cloud", "in the cloud"],
                ],
                negative_phrases=[
                    "correctly understands",
                    "team already understands the split",
                    "already aware of shared responsibility",
                ],
                plausible_source_documents=["waf-sustainability-pillar"],
            ),
        ],
        notes=(
            "Deliberately the smallest brief (1 expected topic) — tests whether the "
            "model still engages seriously with a single, more conceptual/policy-shaped "
            "issue rather than only surfacing findings for brief lists of concrete "
            "misconfigurations like the other briefs."
        ),
    ),
]
