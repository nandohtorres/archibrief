"""Held-out retrieval evaluation set — genuinely separate from EVAL_QUERIES in
eval.py.

Why this exists: the original 18-query set (eval.py) was built by looking at
the same corpus it's used to score, so a retrieval pipeline that happened to
overfit to that corpus's quirks (or to the specific phrasing those 18 queries
use) could still score well without actually generalizing. This set was
authored separately, deliberately avoiding any query/fact already covered by
EVAL_QUERIES, to catch failure modes a real held-out set would catch and the
dev set wouldn't.

Design goals for this set (see ADR-0036 for the original eval design
rationale):
  - Cover all 10 ingested sources, not just the easy 4 HTML pages.
  - Include several queries in the same failure-prone shape as the original
    set's q12: a specific named best practice/control buried inside one of
    the large WAF pillar PDFs, sitting next to generic "Resources" /
    boilerplate chunks (repeated whitepaper links, related-video lists) that
    can crowd out the real answer in a top-k ranking.
  - Include a couple of deliberately adversarial/ambiguous queries: plausible
    phrasing that could plausibly match a decoy chunk in a different
    document, where only one specific chunk (or chunk pair) is actually
    correct.

Chunk IDs below were verified against backend/corpus/data/chunks/ (the
corpus_version="v3", 4,463-chunk corpus); see each query's notes for
specifics. If the corpus is re-chunked, re-verify before reusing this set.

Score it with score_retrieval() from eval.py, which accepts a `queries`
override: pass HOLDOUT_QUERIES to score this set separately from
EVAL_QUERIES.
"""

from backend.corpus.eval import EvalQuery

HOLDOUT_QUERIES: list[EvalQuery] = [
    EvalQuery(
        query_id="h01",
        query="How many iterative phases does the AWS SRA guide's 'Building your security architecture' section describe for building your own security architecture?",
        expected_document_id="aws-security-reference-architecture",
        expected_chunk_ids=["aws-security-reference-architecture-0002"],
        notes="Tests the SRA overview/table-of-contents chunk, distinct from q10's authorship question.",
    ),
    EvalQuery(
        query_id="h02",
        query="Which AWS Security Hub FSBP controls require AWS WAF web ACLs and rule groups to have at least one rule or condition?",
        expected_document_id="aws-fsbp-standard",
        expected_chunk_ids=["aws-fsbp-standard-0012"],
        notes="Distinct FSBP controls from q06/q07 (CloudFront, KMS); this chunk covers WAF.4/6/7/8/10/12.",
    ),
    EvalQuery(
        query_id="h03",
        query="Which CIS AWS Foundations Benchmark v1.4.0 control requires creating a support role to manage incidents with AWS Support?",
        expected_document_id="aws-cis-foundations-mapping",
        expected_chunk_ids=[
            "aws-cis-foundations-mapping-0012",
            "aws-cis-foundations-mapping-0019",
        ],
        notes=(
            "Different CIS version and control (IAM.18, v1.4.0) than q08 "
            "(v5.0.0 support question) and q09 (IAM.6, v1.2.0). Re-verified "
            "2026-09-15 against the 4,463-chunk corpus: chunk 0012 (the "
            "v1.4.0-specific controls list) still directly answers this "
            "query. A later review found that aws-cis-foundations-mapping-0019 "
            "— a cross-version control-mapping table — contains the same "
            "IAM.18 row (and, separately, the IAM.6 row that answers q09 in "
            "eval.py), which is genuine cross-set overlap: a retriever "
            "surfacing 0019 for this query would be giving a correct "
            "answer and should get credit, so 0019 was added here rather "
            "than narrowing the query. q09's own expected_chunk_id "
            "(aws-cis-foundations-mapping-0016) was left as-is since it's "
            "still a valid, more version-specific answer to that query and "
            "the overlap doesn't make it wrong — it just means 0019 is a "
            "second correct answer to both q09 and h03 that isn't listed "
            "under q09. Documented here rather than 'fixed' further since "
            "a comparison table inherently answers many single-version "
            "queries."
        ),
    ),
    EvalQuery(
        query_id="h04",
        query="What IAM tool can generate a fine-grained least-privilege policy based on a role's actual AWS CloudTrail activity?",
        expected_document_id="iam-best-practices",
        expected_chunk_ids=["iam-best-practices-0014"],
        notes="IAM Access Analyzer policy generation — unused chunk in the original set.",
    ),
    EvalQuery(
        query_id="h05",
        query="Do AWS Organizations SCPs and RCPs grant permissions to principals and resources by themselves, or do they only establish guardrails?",
        expected_document_id="iam-best-practices",
        expected_chunk_ids=["iam-best-practices-0019"],
        notes="Tests a specific, checkable factual claim (SCPs/RCPs grant no permissions on their own) rather than a summary question.",
    ),
    EvalQuery(
        query_id="h06",
        query="What does it mean to grant least-privilege permissions when writing an IAM policy that specifies actions, resources, and conditions?",
        expected_document_id="waf-security-pillar",
        expected_chunk_ids=["waf-security-pillar-0264"],
        notes=(
            "Deliberately adversarial: iam-best-practices-0012 ('Apply "
            "least-privilege permissions') defines the same concept in "
            "near-identical language ('grant only the permissions required "
            "to perform a task... actions... resources... conditions') but "
            "is not the expected answer here. Chosen waf-security-pillar as "
            "canonical because the query's phrasing ('specific actions on "
            "specific resources under specific conditions') is closer to "
            "SEC03-BP02's exact wording than the IAM guide's paraphrase. "
            "iam-best-practices-0012 is not used by any query in eval.py or "
            "elsewhere in this set, so it's a genuine untagged decoy — a "
            "pipeline that retrieves it instead should not get credit. "
            "Re-verified 2026-09-15 against the 4,481-chunk corpus (a "
            "further chunking-fragmentation fix shifted boundaries again): "
            "the SEC03-BP02 'Grant least privilege access' definition — "
            "verbatim matching the query's 'specific actions on specific "
            "resources under specific conditions' phrasing — now lives at "
            "0264 alone. iam-best-practices-0012 is still present and still "
            "just as strong a decoy as before (checked directly), so the "
            "adversarial design intent still holds unchanged; kept the "
            "query phrasing as-is rather than disambiguating it, since "
            "resolving the ambiguity by construction is the point of this "
            "test case."
        ),
    ),
    EvalQuery(
        query_id="h07",
        query="Why does REL02-BP04 recommend a hub-and-spoke topology over a many-to-many mesh when connecting multiple VPCs?",
        expected_document_id="waf-reliability-pillar",
        expected_chunk_ids=["waf-reliability-pillar-0216", "waf-reliability-pillar-0218"],
        notes=(
            "Re-verified 2026-09-15 against the 4,463-chunk corpus: the "
            "previously-listed chunk (0050) now contains unrelated "
            "REL01-BP01 service-quota anti-pattern content. The actual "
            "REL02-BP04 recommendation-plus-rationale and benefits text "
            "now live at 0216 and 0218."
        ),
    ),
    EvalQuery(
        query_id="h08",
        query="What is an emergency access process for federated workforce users, and why is it needed if the centralized identity provider fails?",
        expected_document_id="waf-security-pillar",
        expected_chunk_ids=["waf-security-pillar-0275"],
        notes=(
            "SEC03-BP03, unused by the original set (which covers SEC01 "
            "only in this document). Re-verified 2026-09-15 twice — first "
            "against the 4,463-chunk corpus (0279), then again against the "
            "4,481-chunk corpus after a further chunking-fragmentation fix "
            "shifted boundaries again: SEC03-BP03's own definition-plus-"
            "rationale text ('Create a process that allows for emergency "
            "access to your workloads in the unlikely event of an issue "
            "with your centralized identity provider') now lives at 0275."
        ),
    ),
    EvalQuery(
        query_id="h09",
        query="What does OPS03-BP03 say about leadership encouraging team members to escalate issues and concerns?",
        expected_document_id="waf-operational-excellence-pillar",
        expected_chunk_ids=[
            "waf-operational-excellence-pillar-0251",
            "waf-operational-excellence-pillar-0252",
        ],
        notes=(
            "Re-verified 2026-09-15: the previously-listed chunks "
            "(0063-0064) now contain unrelated OPS01-BP04 compliance "
            "content. OPS03-BP03's own definition (0251) and anti-pattern "
            "example, which continues into the next chunk (0252), now live "
            "there — same q12-shaped split as before, just at new IDs."
        ),
    ),
    EvalQuery(
        query_id="h10",
        query="What are common anti-patterns when implementing a caching layer for frequently accessed data, per PERF03-BP05?",
        expected_document_id="waf-performance-efficiency-pillar",
        expected_chunk_ids=["waf-performance-efficiency-pillar-0258"],
        notes=(
            "Unused best practice from the performance pillar; only "
            "PERF01-BP01 (q16) was covered originally. Re-verified "
            "2026-09-15 twice — first against the 4,463-chunk corpus "
            "(0269-0270, the intro), then again after a further chunking-"
            "fragmentation fix shifted boundaries again: PERF03-BP05's "
            "actual anti-pattern list ('You cache data that changes "
            "frequently... You don't monitor the efficiency of your "
            "caching implementation') now lives at 0258 alone."
        ),
    ),
    EvalQuery(
        query_id="h11",
        query="What does COST04-BP05 recommend about enforcing data retention policies when decommissioning resources?",
        expected_document_id="waf-cost-optimization-pillar",
        expected_chunk_ids=["waf-cost-optimization-pillar-0260"],
        notes=(
            "q12-shaped: still sandwiched between generic Resources-section "
            "link boilerplate on both sides. Re-verified 2026-09-15: the "
            "previously-listed chunk (0073) now contains unrelated "
            "COST01-BP06 content. COST04-BP05's own recommendation text "
            "now lives at 0260."
        ),
    ),
    EvalQuery(
        query_id="h12",
        query="Should you back up all of a workload's data in the cloud to reduce its environmental impact?",
        expected_document_id="waf-sustainability-pillar",
        expected_chunk_ids=["waf-sustainability-pillar-0274", "waf-sustainability-pillar-0276"],
        notes=(
            "Deliberately adversarial: SUS04-BP08 actually recommends the "
            "opposite of the naive reading ('back up ONLY when difficult to "
            "recreate', avoiding backup of non-critical data to reduce "
            "storage footprint). A retriever matching on generic "
            "'backup'+'data' vocabulary could easily surface "
            "waf-reliability-pillar's REL09-BP01 'Identify and back up all "
            "data that needs to be backed up', which is topically related "
            "but a wrong-document match for this query. Re-verified "
            "2026-09-15 against the 4,463-chunk corpus: the previously-"
            "listed chunk (0065) now contains unrelated SUS01-BP01 Region-"
            "selection content. SUS04-BP08's own definition and "
            "benefits/rationale text now live at 0274 and 0276."
        ),
    ),
    EvalQuery(
        query_id="h13",
        query="What failover scenarios should be considered when ensuring a sufficient gap between current service quotas and maximum usage?",
        expected_document_id="waf-reliability-pillar",
        expected_chunk_ids=["waf-reliability-pillar-0156"],
        notes=(
            "Re-verified 2026-09-15 against the 4,463-chunk corpus: the "
            "previously-listed chunk (0036) now contains unrelated "
            "availability-percentage-table content from the Definitions "
            "section. REL01-BP06's literal list of failover scenarios to "
            "consider (disrupted VPC, inaccessible subnet, degraded AZ, "
            "etc.) now lives at chunk 0156, surrounded by the same kind of "
            "generic Resources-section boilerplate as before, just at new "
            "chunk IDs."
        ),
    ),
    EvalQuery(
        query_id="h14",
        query="What does COST01-BP07 recommend about staying current with new AWS service releases to find lower-cost options?",
        expected_document_id="waf-cost-optimization-pillar",
        expected_chunk_ids=["waf-cost-optimization-pillar-0080"],
        notes=(
            "Distinct best practice from q17 (COST01-BP01, cost ownership). "
            "Re-verified 2026-09-15: the previously-listed chunk (0027) "
            "now contains unrelated COST01-BP01 KPI-tracking content. "
            "COST01-BP07's own recommendation text now lives at 0080."
        ),
    ),
]
