"""Retrieval evaluation set (ADR-0035/0036) — a frozen set of realistic
queries with known-correct chunks, built against the real ingested corpus.
This must exist and be run before treating any embedding-model choice
(Titan V2 vs. Cohere) or chunking parameter as final; otherwise there is
no way to measure whether retrieval quality is actually good, only whether
the pipeline runs without error.

Chunk IDs below were verified against backend/corpus/data/chunks/ (the
4,463-chunk corpus). If the corpus is re-ingested with a different
chunking policy/version, chunk IDs may shift, so re-verify before reusing
this set against a re-chunked corpus. Each query's notes record how its
expected chunks were chosen.

Known quirks:
- q12's source page is duplicated in the corpus (0005/0006, 0011/0012 and
  0014/0015 are literal duplicates of the same "seven areas" page); the
  list points at the chunks that contain the seven-item list.
- h03's expected chunk in eval_holdout.py's HOLDOUT_QUERIES
  (aws-cis-foundations-mapping-0019, a version-comparison table) is also a
  correct answer to q09 here. This cross-set overlap is left as is, since
  q09's own expected chunk (aws-cis-foundations-mapping-0016) is still a
  valid, more version-specific answer; see h03's notes.
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
        expected_chunk_ids=[
            "iam-best-practices-0005",
            "iam-best-practices-0006",
            "iam-best-practices-0007",
        ],
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
            "Shares a topic with q05 but expects the Security Pillar source. Chunks 0048 and 0052 contain SEC01-BP02's definition and benefits; unrelated shared-responsibility chunks do not count."
        ),
    ),
    EvalQuery(
        query_id="q12",
        query="What are the seven areas that make up security in the cloud per the Well-Architected Security Pillar?",
        expected_document_id="waf-security-pillar",
        expected_chunk_ids=["waf-security-pillar-0012", "waf-security-pillar-0015"],
        notes=(
            "The seven-item list appears in duplicate PDF sections. Chunks 0012 and 0015 contain the actual list; intro-only chunks 0011 and 0014 do not count."
        ),
    ),
    EvalQuery(
        query_id="q13",
        query="What does the SEC01-BP01 best practice recommend about separating workloads using multiple AWS accounts?",
        expected_document_id="waf-security-pillar",
        expected_chunk_ids=["waf-security-pillar-0031", "waf-security-pillar-0038"],
        notes=(
            "SEC01-BP01's recommendation and implementation guidance are in chunks 0031 and 0038. The duplicated seven-areas list does not answer this query."
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
            "OPS01-BP01's recommendation and benefits/implementation guidance are in chunks 0020 and 0025, rather than the generic best-practice-area definition."
        ),
    ),
    EvalQuery(
        query_id="q15",
        query="How does the Well-Architected Framework define the difference between reliability, resiliency, and availability?",
        expected_document_id="waf-reliability-pillar",
        expected_chunk_ids=["waf-reliability-pillar-0029", "waf-reliability-pillar-0031"],
        notes=(
            "Chunks 0029 and 0031 contain the reliability/resiliency and availability definitions; generic shared-responsibility content does not answer the query."
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
            "PERF01-BP01's anti-pattern list spans chunks 0018 and 0021. Chunk 0021 has a misleading implementation-guidance heading but contains continuing anti-pattern bullets."
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
            "Chunks 0021, 0023 and 0024 cover the recommendation, team-structure options and executive sponsorship. Generic cost design principles do not suffice."
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
            "Chunks 0009 and 0010 distinguish AWS's sustainability OF the cloud from customers' sustainability IN the cloud; chunk 0014 elaborates the customer responsibility."
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

    This computes Hit Rate@k (a.k.a. Success@k): the fraction of queries for
    which *at least one* expected chunk appears in the top-k results. This is
    NOT the conventional information-retrieval definition of Recall@k (fraction
    of *all* relevant items retrieved) — for a query with multiple
    expected_chunk_ids, retrieving just one of them still counts as a full hit
    here, so calling it "Recall@5" would overstate what's measured for
    multi-chunk-answer queries. With only 18 queries, treat any single
    percentage from this as a rough signal, not a precise measurement — the 95%
    Wilson confidence interval for 17/18 is roughly 74%-99%.
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
