"""Fetch the approved RAG corpus sources, normalize, and chunk them.

Offline/periodic build-time script (ADR-0036) — not a Lambda, not run
per-request. Writes raw fetched source + resulting chunks to
backend/corpus/data/ for inspection before any embedding/S3 Vectors
upload step, which is separate and not triggered by this script.

The source list is a curated, reviewed set: add a source only after
checking its license and relevance, not ad hoc.
"""

import json
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .chunking import chunk_document
from .normalize import normalize_html
from .normalize_pdf import normalize_pdf

_USER_AGENT = "Mozilla/5.0 (ArchiBrief corpus ingest)"
_DATA_DIR = Path(__file__).parent / "data"
# Bump whenever re-ingestion can change chunk content, boundaries or content_type
# labels (see normalize_pdf.py's _PARSER_VERSION and chunking.py's _CHUNKER_VERSION).
_CORPUS_VERSION = "v3"


@dataclass(frozen=True)
class Source:
    document_id: str
    url: str
    kind: str  # "html" | "pdf"
    source_edition: str | None = None
    # Per AWS's Site Terms (aws.amazon.com/terms/, "LICENSE AND SITE ACCESS"
    # section): docs.aws.amazon.com documentation is CC-BY-SA-4.0. All current
    # sources are docs.aws.amazon.com pages/PDFs, so this is a safe default —
    # override per-source if a future addition uses a different host/license.
    license: str = "CC-BY-SA-4.0"


SOURCES: list[Source] = [
    Source(
        "waf-operational-excellence-pillar",
        "https://docs.aws.amazon.com/pdfs/wellarchitected/latest/operational-excellence-pillar/wellarchitected-operational-excellence-pillar.pdf",
        "pdf",
    ),
    Source(
        "waf-security-pillar",
        "https://docs.aws.amazon.com/pdfs/wellarchitected/latest/security-pillar/wellarchitected-security-pillar.pdf",
        "pdf",
    ),
    Source(
        "waf-reliability-pillar",
        "https://docs.aws.amazon.com/pdfs/wellarchitected/latest/reliability-pillar/wellarchitected-reliability-pillar.pdf",
        "pdf",
    ),
    Source(
        "waf-performance-efficiency-pillar",
        "https://docs.aws.amazon.com/pdfs/wellarchitected/latest/performance-efficiency-pillar/wellarchitected-performance-efficiency-pillar.pdf",
        "pdf",
    ),
    Source(
        "waf-cost-optimization-pillar",
        "https://docs.aws.amazon.com/pdfs/wellarchitected/latest/cost-optimization-pillar/wellarchitected-cost-optimization-pillar.pdf",
        "pdf",
    ),
    Source(
        "waf-sustainability-pillar",
        "https://docs.aws.amazon.com/pdfs/wellarchitected/latest/sustainability-pillar/wellarchitected-sustainability-pillar.pdf",
        "pdf",
    ),
    Source(
        "aws-fsbp-standard",
        "https://docs.aws.amazon.com/securityhub/latest/userguide/fsbp-standard.html",
        "html",
    ),
    Source(
        "aws-security-reference-architecture",
        "https://docs.aws.amazon.com/prescriptive-guidance/latest/security-reference-architecture/introduction.html",
        "html",
    ),
    Source(
        "iam-best-practices",
        "https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html",
        "html",
    ),
    Source(
        "aws-cis-foundations-mapping",
        "https://docs.aws.amazon.com/securityhub/latest/userguide/cis-aws-foundations-benchmark.html",
        "html",
    ),
]


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def ingest_source(source: Source, *, retrieved_at: datetime) -> dict:
    raw_dir = _DATA_DIR / "raw"
    chunks_dir = _DATA_DIR / "chunks"
    raw_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    content = fetch(source.url)
    raw_path = raw_dir / f"{source.document_id}.{source.kind}"
    raw_path.write_bytes(content)

    if source.kind == "html":
        snapshot = normalize_html(
            content.decode("utf-8", errors="replace"),
            document_id=source.document_id,
            source_url=source.url,
            retrieved_at=retrieved_at,
            source_edition=source.source_edition,
            license=source.license,
        )
    else:
        snapshot = normalize_pdf(
            content,
            document_id=source.document_id,
            source_url=source.url,
            retrieved_at=retrieved_at,
            source_edition=source.source_edition,
            license=source.license,
        )

    chunks = chunk_document(snapshot, corpus_version=_CORPUS_VERSION)
    chunks_path = chunks_dir / f"{source.document_id}.json"
    chunks_path.write_text(
        json.dumps([chunk.model_dump(mode="json") for chunk in chunks], indent=2),
        encoding="utf-8",
    )

    return {
        "document_id": source.document_id,
        "sections": len(snapshot.sections),
        "chunks": len(chunks),
        "total_tokens": sum(c.token_count for c in chunks),
    }


def main() -> None:
    retrieved_at = datetime.now(UTC)
    results = []
    for source in SOURCES:
        try:
            result = ingest_source(source, retrieved_at=retrieved_at)
            results.append(result)
            print(
                f"OK   {result['document_id']:40s} {result['sections']:3d} sections  "
                f"{result['chunks']:4d} chunks  {result['total_tokens']:7d} tokens"
            )
        except Exception as error:  # noqa: BLE001
            print(f"FAIL {source.document_id:40s} {error}")

    total_chunks = sum(r["chunks"] for r in results)
    total_tokens = sum(r["total_tokens"] for r in results)
    print(
        f"\n{len(results)}/{len(SOURCES)} sources ingested — {total_chunks} chunks, "
        f"{total_tokens} total tokens"
    )


if __name__ == "__main__":
    main()
