"""LangGraph node: Retrieve.

Runs inside the AgentCore Runtime + LangGraph subworkflow (ADR-0028), NOT
as a standalone Lambda.

Embeds query context via Titan V2 (working baseline candidate pending
evaluation, NOT a final/locked choice — ADR-0035), searches S3 Vectors,
returns top-k chunks with the full citation metadata set required by
ADR-0027/ADR-0036. Also does a deterministic/lexical companion lookup for
exact AWS identifiers/control names (ADR-0036), since vector recall alone
can miss them.

The Bedrock and S3 Vectors calls are isolated in backend.shared.clients, so
this node's retrieval/merge logic is testable against a stubbed client.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.shared.clients import BedrockEmbeddingClient, S3VectorsClient

# The [A-Z]{2,}\d{1,3}-[A-Z]{2,}\d{1,3} branch matches Well-Architected
# best-practice IDs like "SEC01-BP01" or "COST01-BP01", which have digits
# on both sides of the hyphen and so are missed by the plain
# [A-Z]{2,}-\d+ branch.
AWS_IDENTIFIER_PATTERN = re.compile(
    r"\b(?:AWS::[A-Za-z0-9]+::[A-Za-z0-9]+|aws_[a-z0-9_]+"
    r"|[A-Z]{2,}\d{1,3}-[A-Z]{2,}\d{1,3}|[A-Z]{2,}-\d+(?:\.\d+)?)\b"
)


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    text: str
    source_url: str
    content_hash: str
    heading_path: str
    corpus_version: str
    score: float
    match_type: str  # "vector" | "lexical"
    # Citation-reproducibility fields (ADR-0027/ADR-0036) carried over from
    # the Chunk model (backend/corpus/models.py); reason_node needs them to
    # build a Citation without a second lookup.
    retrieved_at: str = ""
    source_edition: str | None = None
    parser_version: str = ""
    content_type: str = "prose"


def extract_lexical_terms(query: str) -> list[str]:
    return sorted(set(AWS_IDENTIFIER_PATTERN.findall(query)))


def lexical_companion_lookup(
    lexical_terms: list[str], corpus_index: dict[str, list[dict]]
) -> list[RetrievedChunk]:
    """corpus_index maps an exact identifier -> list of chunk metadata dicts.

    corpus_index is built from the curated corpus chunks (see
    backend/corpus/lexical_index.py).
    """
    results: list[RetrievedChunk] = []
    for term in lexical_terms:
        for chunk in corpus_index.get(term, []):
            results.append(
                RetrievedChunk(
                    chunk_id=chunk["chunk_id"],
                    document_id=chunk["document_id"],
                    text=chunk["text"],
                    source_url=chunk["source_url"],
                    content_hash=chunk["content_hash"],
                    heading_path=chunk["heading_path"],
                    corpus_version=chunk["corpus_version"],
                    score=1.0,
                    match_type="lexical",
                    retrieved_at=chunk.get("retrieved_at", ""),
                    source_edition=chunk.get("source_edition"),
                    parser_version=chunk.get("parser_version", ""),
                    content_type=chunk.get("content_type", "prose"),
                )
            )
    return results


def vector_search(
    query_text: str,
    embedding_client: BedrockEmbeddingClient,
    vectors_client: S3VectorsClient,
    top_k: int = 8,
) -> list[RetrievedChunk]:
    query_vector = embedding_client.embed(query_text)
    matches = vectors_client.query_vectors(query_vector=query_vector, top_k=top_k)

    results = []
    for match in matches:
        metadata = match.get("metadata", {})
        # embed.py's to_vector_record() stores the raw chunk dict as metadata
        # verbatim, so heading_path arrives here as list[str] (Chunk's real
        # type), never the pre-joined string lexical_index.py produces for
        # the lexical path — join it the same way here so RetrievedChunk's
        # heading_path is consistently a str regardless of match_type.
        raw_heading_path = metadata.get("heading_path", [])
        heading_path = (
            " > ".join(raw_heading_path) if isinstance(raw_heading_path, list) else raw_heading_path
        )
        results.append(
            RetrievedChunk(
                chunk_id=metadata.get("chunk_id", match.get("key", "")),
                document_id=metadata.get("document_id", ""),
                text=metadata.get("text", ""),
                source_url=metadata.get("source_url", ""),
                content_hash=metadata.get("content_hash", ""),
                heading_path=heading_path,
                corpus_version=metadata.get("corpus_version", ""),
                score=match.get("distance", 0.0),
                match_type="vector",
                retrieved_at=metadata.get("retrieved_at", ""),
                source_edition=metadata.get("source_edition"),
                parser_version=metadata.get("parser_version", ""),
                content_type=metadata.get("content_type", "prose"),
            )
        )
    return results


def merge_results(
    vector_results: list[RetrievedChunk], lexical_results: list[RetrievedChunk]
) -> list[RetrievedChunk]:
    seen: set[str] = set()
    merged: list[RetrievedChunk] = []
    for chunk in [*lexical_results, *vector_results]:
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        merged.append(chunk)
    return merged


# Searching with the workload brief alone returns whatever is closest to
# the brief. A vague or junk brief ("testyy") brought back only general
# Security Pillar design principles, and every finding cited them. These
# fixed searches, picked by which resource types the code declares, reach
# the service-specific guidance (Reliability pillar, Foundational
# Security Best Practices, IAM best practices) that findings are about.
# The text is ArchiBrief's own, never the submitter's. Ordered by risk:
# when more types match than MAX_TOPICS, the earlier ones are searched.
TOPIC_QUERIES: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("aws_iam_role", "aws_iam_openid_connect_provider"),
        (
            "IAM role trust policies: cross-account access with an external ID, "
            "OIDC federation subject conditions, least privilege for roles"
        ),
    ),
    (
        ("aws_iam_policy", "aws_iam_role_policy", "aws_iam_group_policy", "aws_iam_user_policy"),
        (
            "IAM least privilege permissions and privilege escalation through "
            "iam:PassRole and broad wildcard actions"
        ),
    ),
    (
        ("aws_ecs_task_definition",),
        (
            "ECS task definitions should not pass secrets as plaintext environment "
            "variables; use Secrets Manager or Parameter Store"
        ),
    ),
    (
        ("aws_cloudfront_distribution",),
        (
            "CloudFront should encrypt traffic to custom origins with HTTPS and "
            "restrict direct access to the origin"
        ),
    ),
    (
        ("aws_lb_listener", "aws_lb", "aws_alb"),
        (
            "Load balancer listeners should use HTTPS with a current TLS security "
            "policy and redirect HTTP to HTTPS"
        ),
    ),
    (
        ("aws_rds_cluster", "aws_db_instance"),
        (
            "Database high availability across Availability Zones, automated "
            "backups, deletion protection and encryption in transit"
        ),
    ),
    (
        ("aws_elasticache_replication_group", "aws_elasticache_cluster"),
        (
            "ElastiCache encryption in transit, authentication and automatic "
            "failover across Availability Zones"
        ),
    ),
    (
        ("aws_sqs_queue",),
        (
            "SQS dead-letter queues, message retention, monitoring failed "
            "messages and encryption at rest"
        ),
    ),
    (
        ("aws_nat_gateway", "aws_subnet"),
        (
            "Avoid single points of failure: deploy across multiple Availability "
            "Zones, including one NAT gateway per zone"
        ),
    ),
    (
        ("aws_security_group", "aws_security_group_rule", "aws_vpc_security_group_ingress_rule"),
        (
            "Security groups should not allow unrestricted ingress from the "
            "internet to databases or administrative ports"
        ),
    ),
    (
        ("aws_cloudtrail",),
        "CloudTrail multi-Region trails, log file validation and encryption",
    ),
    (
        ("aws_secretsmanager_secret", "aws_kms_key"),
        "Rotate secrets and encryption keys automatically",
    ),
    (
        ("aws_ecr_repository",),
        "Container image scanning and immutable image tags",
    ),
    (
        ("aws_cloudwatch_metric_alarm", "aws_cloudwatch_log_group"),
        "Monitor workload health with alarms and set log retention",
    ),
)
MAX_TOPICS = 8
# Cost guidance, searched on top of the risk topics so they never crowd it
# out. Without it every cost finding in a review cited the one general
# budgeting chunk the brief happened to match (2026-10-28).
COST_TOPIC_QUERIES: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        (
            "aws_instance",
            "aws_db_instance",
            "aws_rds_cluster_instance",
            "aws_opensearch_domain",
            "aws_elasticsearch_domain",
            "aws_elasticache_replication_group",
            "aws_elasticache_cluster",
            "aws_lambda_function",
            "aws_ecs_service",
            "aws_eks_node_group",
            "aws_launch_template",
        ),
        (
            "Select resource type, size, and number based on data: right-size "
            "compute, database and search instances to measured demand"
        ),
    ),
    (
        (
            "aws_dynamodb_table",
            "aws_db_instance",
            "aws_rds_cluster",
            "aws_instance",
            "aws_nat_gateway",
            "aws_kinesis_stream",
        ),
        (
            "Pricing model analysis: on-demand versus provisioned capacity, "
            "Savings Plans and Reserved Instances"
        ),
    ),
    (
        ("aws_s3_bucket", "aws_cloudwatch_log_group", "aws_efs_file_system"),
        "Enforce data retention policies and decommission unused resources and storage",
    ),
)
MAX_COST_TOPICS = 2
TOPIC_TOP_K = 3
# Embedding plus vector query for the brief and each topic: the most
# service calls one retrieval makes, for evaluation call budgets.
MAX_RETRIEVAL_CALLS = 2 * (1 + MAX_TOPICS + MAX_COST_TOPICS)


def _matching(
    table: tuple[tuple[tuple[str, ...], str], ...], declared: set, limit: int
) -> list[str]:
    return [query for types, query in table if any(t in declared for t in types)][:limit]


def topic_queries(terraform_resources: object) -> list[str]:
    """Fixed search texts for the resource types the submitted code declares."""
    resources = (
        terraform_resources.get("resources") if isinstance(terraform_resources, dict) else None
    )
    declared = {r.get("type") for r in resources or [] if isinstance(r, dict)}
    return _matching(TOPIC_QUERIES, declared, MAX_TOPICS) + _matching(
        COST_TOPIC_QUERIES, declared, MAX_COST_TOPICS
    )


def retrieve_node(state: dict) -> dict:
    query_text = state["retrieval_query"]
    embedding_client: BedrockEmbeddingClient = state["embedding_client"]
    vectors_client: S3VectorsClient = state["vectors_client"]
    corpus_index: dict[str, list[dict]] = state.get("lexical_corpus_index", {})

    lexical_terms = extract_lexical_terms(query_text)
    lexical_results = lexical_companion_lookup(lexical_terms, corpus_index)
    vector_results = vector_search(query_text, embedding_client, vectors_client)
    # "Go deeper" already searches with a finding-specific query.
    if not state.get("deep_mode"):
        for topic in topic_queries(state.get("terraform_resources")):
            vector_results += vector_search(
                topic, embedding_client, vectors_client, top_k=TOPIC_TOP_K
            )
    merged = merge_results(vector_results, lexical_results)

    return {
        **state,
        "retrieved_chunks": [chunk.__dict__ for chunk in merged],
    }
