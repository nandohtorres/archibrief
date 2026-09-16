"""Retrieval evaluation set (ADR-0035/0036) — a frozen set of realistic
queries with known-correct chunks, built against the real ingested corpus
(2026-09-11). This must exist and be run before treating any
embedding-model choice (Titan V2 vs. Cohere) or chunking parameter as
final — otherwise there is no way to measure whether retrieval quality is
actually good, only whether the pipeline runs without error.

Chunk IDs below were verified against backend/corpus/data/chunks/ at
authoring time. If the corpus is re-ingested with a different chunking
policy/version, chunk IDs may shift — re-verify before reusing this set
against a re-chunked corpus.

Re-verified 2026-09-14 after the PDF-normalization fixes in
normalize_pdf.py (see Work-Project-Issues-Log, 2026-09-14 follow-on
entry). The 4 HTML-sourced queries (q01-q10) were unaffected — HTML
normalization/chunking wasn't touched, and their chunk IDs matched
exactly. The 8 WAF-PDF-sourced queries (q11-q18) were re-checked against
the corrected corpus (1,073 total chunks, down from 24,897 in the
polluted run): q12 and q15 happened to keep the same IDs, the rest
shifted because sections that used to be wrongly merged or wrongly
capped are now split/extended correctly.

Re-verified again 2026-09-15 against the final 4,463-chunk corpus (after
the chunk-typing fix and the follow-on procedure-splitting/table/code-
detection/absorption-bug fix grew the corpus 1,073 -> 3,327 -> 4,463).
All 10 HTML/short-document queries (q01-q10) still matched exactly. All 8
WAF-PDF queries (q11-q18) had drifted again and were re-pointed at the
chunks that now actually contain the answer text — see each query's
notes for what changed. q12 was also found to have a second, previously
undocumented duplicate-chunk pair (0011/0012 and 0014/0015 are literal
duplicates of the same "seven areas" page) in addition to the 0005/0006
pair found in the 2026-09-14 review; the list now points at the two list
chunks that actually contain the seven-item list. h03's expected chunk
in eval_holdout.py's HOLDOUT_QUERIES was found to also be a correct
answer to q09 in this file (aws-cis-foundations-mapping-0019, a version-
comparison table): this is left as a known cross-set semantic overlap
rather than "fixed" here, since q09's own expected_chunk_id
(aws-cis-foundations-mapping-0016) is still a valid, more version-
specific answer and changing it isn't necessary — see eval_holdout.py's
h03 notes for the full writeup of the decision.
"""

from pydantic import BaseModel


class EvalQuery(BaseModel):
    """One evaluation query: a realistic question a review's Retrieve step
    might issue, plus the chunk(s) that count as a correct retrieval."""

    query_id: str
    query: str
    expected_document_id: str
    expected_chunk_ids: list[str]
    notes: str | None = None


EVAL_QUERIES: list[EvalQuery] = [
    EvalQuery(
        query_id="q01",
        query="Should human users sign in with long-term IAM user credentials, or federate through an identity provider?",
        expected_document_id="iam-best-practices",
        expected_chunk_ids=["iam-best-practices-0003"],
    ),
    EvalQuery(
        query_id="q02",
        query="How can a workload running outside of AWS get temporary AWS credentials instead of long-term access keys?",
        expected_document_id="iam-best-practices",
        expected_chunk_ids=["iam-best-practices-0005", "iam-best-practices-0006", "iam-best-practices-0007"],
        notes="Answer spans a few adjacent chunks under the same heading; any one counts as a hit.",
    ),
    EvalQuery(
        query_id="q03",
        query="When is it acceptable to require MFA for an IAM user instead of relying on temporary role credentials?",
        expected_document_id="iam-best-practices",
        expected_chunk_ids=["iam-best-practices-0008"],
    ),
    EvalQuery(
        query_id="q04",
        query="What's the recommended practice for rotating long-term IAM access keys when they can't be avoided?",
        expected_document_id="iam-best-practices",
        expected_chunk_ids=["iam-best-practices-0009", "iam-best-practices-0010"],
    ),
    EvalQuery(
        query_id="q05",
        query="How should the AWS account root user's credentials be protected?",
        expected_document_id="iam-best-practices",
        expected_chunk_ids=["iam-best-practices-0011"],
        notes="Deliberately ambiguous with q11 (WAF Security Pillar SEC01-BP02) — good test of whether retrieval correctly disambiguates near-duplicate topics across two different sources.",
    ),
    EvalQuery(
        query_id="q06",
        query="Which AWS Foundational Security Best Practices control addresses CloudFront distributions and origin failover?",
        expected_document_id="aws-fsbp-standard",
        expected_chunk_ids=["aws-fsbp-standard-0003"],
    ),
    EvalQuery(
        query_id="q07",
        query="Which FSBP control restricts KMS customer managed policies from allowing decryption actions on all resources?",
        expected_document_id="aws-fsbp-standard",
        expected_chunk_ids=["aws-fsbp-standard-0008"],
    ),
    EvalQuery(
        query_id="q08",
        query="What is the most recent version of the CIS AWS Foundations Benchmark that Security Hub CSPM supports?",
        expected_document_id="aws-cis-foundations-mapping",
        expected_chunk_ids=["aws-cis-foundations-mapping-0002"],
    ),
    EvalQuery(
        query_id="q09",
        query="Which CIS AWS Foundations Benchmark v1.2.0 control requires hardware MFA for the root user?",
        expected_document_id="aws-cis-foundations-mapping",
        expected_chunk_ids=["aws-cis-foundations-mapping-0016"],
    ),
    EvalQuery(
        query_id="q10",
        query="Who authored the AWS Security Reference Architecture, and what is it?",
        expected_document_id="aws-security-reference-architecture",
        expected_chunk_ids=["aws-security-reference-architecture-0001"],
    ),
    EvalQuery(
        query_id="q11",
        query="What Well-Architected Security Pillar best practice covers securing the account root user and its properties?",
        expected_document_id="waf-security-pillar",
        expected_chunk_ids=["waf-security-pillar-0048", "waf-security-pillar-0052"],
        notes=(
            "Deliberately ambiguous with q05 (IAM best practices root-user "
            "guidance) — same underlying topic, two different sources. "
            "Re-verified 2026-09-15 against the 4,463-chunk corpus: the "
            "previously-listed chunks (0015-0019) now contain unrelated "
            "'Shared responsibility' content — SEC01-BP02's actual "
            "definition/desired-outcome and benefits/risk text now live at "
            "0048 and 0052."
        ),
    ),
    EvalQuery(
        query_id="q12",
        query="What are the seven areas that make up security in the cloud per the Well-Architected Security Pillar?",
        expected_document_id="waf-security-pillar",
        expected_chunk_ids=["waf-security-pillar-0012", "waf-security-pillar-0015"],
        notes=(
            "Re-verified 2026-09-15 against the 4,463-chunk corpus: the "
            "intro sentence ('Security in the cloud is composed of seven "
            "areas:') and the seven-item list are now split into separate "
            "chunks, and the whole intro+list pair is duplicated twice in a "
            "row in this document (0011/0012 under heading 'Definition', "
            "then 0014/0015 under heading 'Shared responsibility' — same "
            "text, different heading_path, a PDF-parsing artifact). Listed "
            "here are the two list chunks (0012 and 0015) that actually "
            "contain the seven-item list verbatim; the intro-only chunks "
            "(0011, 0014) were not included since they don't contain the "
            "list itself. Supersedes the 2026-09-14 finding about 0005/0006 "
            "being duplicate siblings — those chunk IDs no longer contain "
            "this content at all after the follow-on rechunk."
        ),
    ),
    EvalQuery(
        query_id="q13",
        query="What does the SEC01-BP01 best practice recommend about separating workloads using multiple AWS accounts?",
        expected_document_id="waf-security-pillar",
        expected_chunk_ids=["waf-security-pillar-0031", "waf-security-pillar-0038"],
        notes=(
            "Re-verified 2026-09-15: the previously-listed chunks "
            "(0012-0014) now contain the duplicated 'seven areas' content "
            "(see q12), not SEC01-BP01. The actual recommendation and "
            "implementation guidance now live at 0031 and 0038."
        ),
    ),
    EvalQuery(
        query_id="q14",
        query="What does OPS01-BP01 say about evaluating external customer needs for a workload?",
        expected_document_id="waf-operational-excellence-pillar",
        expected_chunk_ids=[
            "waf-operational-excellence-pillar-0020",
            "waf-operational-excellence-pillar-0025",
        ],
        notes=(
            "Re-verified 2026-09-15: the previously-listed chunks "
            "(0010-0012) now contain the 'four best practice areas' "
            "definition content, not OPS01-BP01. The actual recommendation "
            "and benefits/implementation-guidance text now live at 0020 "
            "and 0025."
        ),
    ),
    EvalQuery(
        query_id="q15",
        query="How does the Well-Architected Framework define the difference between reliability, resiliency, and availability?",
        expected_document_id="waf-reliability-pillar",
        expected_chunk_ids=["waf-reliability-pillar-0029", "waf-reliability-pillar-0031"],
        notes=(
            "Re-verified 2026-09-15: the previously-listed chunks "
            "(0009-0010) now contain unrelated Shared-Responsibility-for-"
            "Resiliency content. The actual resiliency/reliability "
            "definition and the availability definition now live at 0029 "
            "and 0031."
        ),
    ),
    EvalQuery(
        query_id="q16",
        query="What are typical anti-patterns for PERF01-BP01, learning about and understanding available cloud services and features?",
        expected_document_id="waf-performance-efficiency-pillar",
        expected_chunk_ids=[
            "waf-performance-efficiency-pillar-0018",
            "waf-performance-efficiency-pillar-0021",
        ],
        notes=(
            "Re-verified 2026-09-15: the previously-listed chunk (0005) "
            "now contains an unrelated topic list. The anti-patterns are "
            "split across two list chunks under PERF01-BP01 (0018 and "
            "0021 — the latter's heading_path is mislabeled 'Implementation "
            "guidance/Implementation steps' by the chunker but its content "
            "is still 'You...' anti-pattern bullets continuing the same "
            "list)."
        ),
    ),
    EvalQuery(
        query_id="q17",
        query="What does COST01-BP01 recommend about establishing ownership of cost optimization within an organization?",
        expected_document_id="waf-cost-optimization-pillar",
        expected_chunk_ids=[
            "waf-cost-optimization-pillar-0021",
            "waf-cost-optimization-pillar-0023",
            "waf-cost-optimization-pillar-0024",
        ],
        notes=(
            "Re-verified 2026-09-15: the previously-listed chunks "
            "(0009-0011) now contain unrelated paper-introduction/design-"
            "principles content. The actual recommendation, team-structure "
            "options, and executive-sponsorship guidance now live at 0021, "
            "0023, and 0024."
        ),
    ),
    EvalQuery(
        query_id="q18",
        query="What is the shared responsibility model for environmental sustainability of the cloud?",
        expected_document_id="waf-sustainability-pillar",
        expected_chunk_ids=[
            "waf-sustainability-pillar-0009",
            "waf-sustainability-pillar-0010",
            "waf-sustainability-pillar-0014",
        ],
        notes=(
            "Re-verified 2026-09-15: the previously-listed chunks (0005, "
            "0007) now contain unrelated paper-introduction and Scope "
            "1/2/3 emissions content. The actual shared-responsibility "
            "split (0009-0010: AWS is responsible for sustainability OF "
            "the cloud, customers for sustainability IN the cloud) plus "
            "the 'in the cloud' elaboration (0014) now live there."
        ),
    ),
]


def score_retrieval(
    predictions: dict[str, list[str]],
    queries: list[EvalQuery] = EVAL_QUERIES,
    k: int = 5,
) -> dict:
    """Score a retrieval pipeline's output against this eval set.

    `predictions` maps query_id -> the ordered list of chunk_ids the
    pipeline actually retrieved for that query.

    This computes Hit Rate@k (a.k.a. Success@k): the fraction of queries
    for which *at least one* expected chunk appears in the top-k results.
    This is NOT the conventional information-retrieval definition of
    Recall@k (fraction of *all* relevant items retrieved) — for a query
    with multiple expected_chunk_ids, retrieving just one of them still
    counts as a full hit here. Named/labeled precisely per a 2026-09-14
    Codex review finding: the result had been reported as "Recall@5"
    everywhere, which overstates what's actually measured for
    multi-chunk-answer queries. With only 18 queries, treat any single
    percentage from this as a rough signal, not a precise measurement —
    the 95% Wilson confidence interval for 17/18 is roughly 74%-99%.
    """
    per_query: list[dict] = []
    hits = 0
    for eval_query in queries:
        retrieved = predictions.get(eval_query.query_id, [])[:k]
        expected = set(eval_query.expected_chunk_ids)
        hit = any(chunk_id in expected for chunk_id in retrieved)
        hits += hit
        per_query.append(
            {
                "query_id": eval_query.query_id,
                "hit": hit,
                "retrieved": retrieved,
                "expected": eval_query.expected_chunk_ids,
            }
        )
    total = len(queries)
    return {
        "hit_rate_at_k": hits / total if total else 0.0,
        "k": k,
        "total_queries": total,
        "hits": hits,
        "per_query": per_query,
    }
