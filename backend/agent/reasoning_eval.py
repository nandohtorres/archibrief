"""Reasoning-quality evaluation set for reason_node — a genuinely different
question from what validate_reason_node.py checks.

validate_reason_node.py (and reason_node's own server-side verification,
see backend/agent/nodes/reason.py) proves TRUSTWORTHINESS: is a returned
citation real (the chunk_id was actually retrieved, the quote actually
appears in that chunk's text)? It says nothing about QUALITY: did the
model find the issues a competent human reviewer would expect from a given
workload brief, did it invent anything, and is a technically-real citation
actually good support for the claim it's attached to (the "citation-shaped
hallucination" pattern flagged in Work-Project-Issues-Log.md's 2026-09-16
entries — a citation can be real and still not fully support the finding's
prose). The first real end-to-end run (2026-09-16) surfaced exactly this
gap: the model returned only 1 finding for a workload brief that plausibly
supports at least 3, and nothing measured whether that was a real
completeness problem or just that one brief.

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
  to a different artifact. Deliberately NOT an LLM-judge: grading Claude's
  output with another Claude call adds real cost, a second unverified
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
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from backend.shared.models.finding import Finding


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
    expected_findings: list[ExpectedFinding]
    notes: str | None = None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()


def _finding_covers_topic(finding: Finding, expected: ExpectedFinding) -> bool:
    haystack = _normalize(f"{finding.finding} {finding.evidence} {finding.risk_impact}")
    for group in expected.keyword_groups:
        if not any(keyword.lower() in haystack for keyword in group):
            return False
    return True


def score_reasoning(
    findings: list[Finding],
    brief: ReasoningEvalBrief,
) -> dict:
    """Scores one brief's actual model-produced findings (NOT including the
    server-attached rule_findings — pass only what parse_model_findings()
    returned, matching what expected_findings was authored against) against
    its expected_findings.

    Returns per-topic coverage (which finding, if any, covered it, and
    whether that finding's citation's document_id was in the topic's
    plausible_source_documents), plus a list of findings that matched no
    expected topic at all (see module docstring: reported for human
    review, never auto-scored as wrong)."""
    topic_hits: list[dict] = []
    matched_finding_ids: set[str] = set()

    for expected in brief.expected_findings:
        covering = [f for f in findings if _finding_covers_topic(f, expected)]
        if covering:
            matched_finding_ids.update(f.finding_id for f in covering)
            citation_relevant = any(
                f.citation is not None and f.citation.document_id in expected.plausible_source_documents
                for f in covering
            )
        else:
            citation_relevant = None  # not applicable — nothing matched
        topic_hits.append(
            {
                "topic_id": expected.topic_id,
                "description": expected.description,
                "covered": bool(covering),
                "covered_by_finding_ids": [f.finding_id for f in covering],
                "citation_from_plausible_source": citation_relevant,
            }
        )

    unmatched_findings = [
        {"finding_id": f.finding_id, "finding": f.finding, "category": f.category.value}
        for f in findings
        if f.finding_id not in matched_finding_ids
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
        retrieval_query=(
            "S3 bucket versioning for critical data recovery and root user MFA best practices"
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
                description="No CloudTrail trail exists, so there's no audit log of API/data access.",
                keyword_groups=[["cloudtrail"], ["log", "audit", "logging"]],
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
                description=(
                    "A single Lambda reads/writes directly to the bucket with no mention of "
                    "least-privilege scoping — likely overly broad IAM permissions."
                ),
                keyword_groups=[["lambda"], ["least privilege", "least-privilege", "iam", "permission"]],
                plausible_source_documents=["waf-security-pillar", "iam-best-practices"],
            ),
        ],
        notes=(
            "Same brief as validate_reason_node.py's scripted run (2026-09-16 first "
            "success) — root-mfa was the one topic that run actually covered; "
            "no-cloudtrail and lambda-broad-access were the two it did NOT surface, "
            "which is the exact completeness gap this eval exists to measure going "
            "forward, not just observe once."
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
        retrieval_query=(
            "establishing cost ownership across accounts and rightsizing EC2 instances "
            "based on utilization"
        ),
        expected_findings=[
            ExpectedFinding(
                topic_id="no-cost-ownership",
                category="cost",
                description="No cost owner or tagging policy — nobody accountable for spend.",
                keyword_groups=[["cost"], ["owner", "ownership", "accountab"]],
                plausible_source_documents=["waf-cost-optimization-pillar"],
            ),
            ExpectedFinding(
                topic_id="oversized-instances",
                category="cost",
                description="EC2 instances oversized without utilization monitoring — rightsizing opportunity.",
                keyword_groups=[["rightsiz", "oversiz", "right-siz", "instance size", "utilization"]],
                plausible_source_documents=["waf-cost-optimization-pillar", "waf-performance-efficiency-pillar"],
            ),
            ExpectedFinding(
                topic_id="no-commitment-discounts",
                category="cost",
                description="No Savings Plans/Reserved Instances used despite steady-state workloads.",
                keyword_groups=[["savings plan", "reserved instance", "commitment"]],
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
                plausible_source_documents=["waf-reliability-pillar"],
            ),
            ExpectedFinding(
                topic_id="backups-disabled",
                category="recovery",
                description="Automated RDS backups are disabled — no point-in-time recovery.",
                keyword_groups=[["backup"], ["disabled", "not enabled", "no automated"]],
                plausible_source_documents=["waf-reliability-pillar"],
            ),
            ExpectedFinding(
                topic_id="untested-restore",
                category="recovery",
                description="Restore from backup has never been tested — an unverified recovery path.",
                keyword_groups=[["restore", "recovery"], ["test", "tested", "untested", "verif"]],
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
        workload_brief=(
            "Our data science team spins up EC2 instances for training jobs directly from "
            "personal IAM user access keys that don't expire, shared across the team via a "
            "spreadsheet. The training data lives in an S3 bucket with a bucket policy that "
            "grants s3:* to the account's entire IAM user group."
        ),
        retrieval_query="long-term IAM access keys and overly broad S3 bucket policy permissions",
        expected_findings=[
            ExpectedFinding(
                topic_id="shared-long-term-keys",
                category="iam",
                description="Long-term IAM access keys shared across a team instead of temporary/federated credentials.",
                keyword_groups=[["access key", "long-term", "long term"], ["shar", "federat", "temporary"]],
                plausible_source_documents=["iam-best-practices", "waf-security-pillar"],
            ),
            ExpectedFinding(
                topic_id="wildcard-bucket-policy",
                category="exposure",
                description="Bucket policy grants s3:* to an entire IAM group — violates least privilege.",
                keyword_groups=[["s3:*", "wildcard", "all actions", "full access"], ["least privilege", "least-privilege"]],
                plausible_source_documents=["waf-security-pillar", "iam-best-practices", "aws-fsbp-standard"],
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
                keyword_groups=[["dev", "staging", "non-production", "non production"], ["schedul", "shut down", "shutdown", "24/7"]],
                plausible_source_documents=["waf-cost-optimization-pillar", "waf-sustainability-pillar"],
            ),
            ExpectedFinding(
                topic_id="no-spot-for-fault-tolerant",
                category="cost",
                description="Fault-tolerant, restartable batch jobs don't use Spot Instances.",
                keyword_groups=[["spot instance", "spot"], ["fault-toleran", "fault toleran", "restart"]],
                plausible_source_documents=["waf-cost-optimization-pillar", "waf-performance-efficiency-pillar"],
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
                keyword_groups=[["shared responsibility"], ["sustainab", "carbon", "of the cloud", "in the cloud"]],
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
