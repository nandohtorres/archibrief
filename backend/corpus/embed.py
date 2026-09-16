"""Embed the ingested corpus via Titan V2 and populate S3 Vectors (ADR-0035).

Offline/build-time batch job — run locally, once, on Fernando's explicit
go-ahead (this calls Bedrock for real and spends real money). Not a
Lambda, not run per-request. Reads chunks written by `ingest.py` under
backend/corpus/data/chunks/, embeds each chunk's text, and writes the
resulting vector + full citation metadata into the S3 Vectors index
created by infra/modules/s3-vectors (dimension/distance metric locked at
creation time — must match Titan V2's 1024-dim output exactly).

Failure-mode design (Codex-reviewed 2026-09-14, independently verified —
see Work-Project-Deployment-Roadmap.md RAG foundation section):

- Chunks are processed in bounded waves of _PUT_VECTORS_BATCH_SIZE, not
  submitted all at once. A ThreadPoolExecutor's context manager only
  calls shutdown(wait=True) with cancel_futures=False by default, so an
  exception partway through does NOT stop already-queued work — it keeps
  running (and billing Bedrock) to completion. Bounding submission to one
  wave at a time caps the blast radius of that behavior to one wave
  instead of the whole corpus, and each wave explicitly cancels its own
  remaining futures the moment anything fails.
- The first wave is a single chunk — a cheap smoke test that catches
  wrong index/dimension/permissions/metadata-shape errors for the price
  of one embedding instead of a full batch.
- Each wave's embeddings are persisted to a local pending-batch file
  BEFORE the PutVectors call, so a crash between "Bedrock call succeeded"
  and "checkpoint recorded it" doesn't require re-paying for that wave —
  resuming replays the pending batch (S3 Vectors overwrites by key, so a
  replayed PutVectors is safe) before continuing normal processing.
- The checkpoint is written atomically (temp file + os.replace) and is
  bound to the target bucket/index/model, plus a per-chunk content_hash
  — so a recreated/emptied index, a different target, or a chunk whose
  source text changed under the same chunk_id can't be silently skipped
  by a stale checkpoint from a previous run.
"""

import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError

from backend.shared.clients import BedrockEmbeddingClient, S3VectorsClient

_DATA_DIR = Path(__file__).parent / "data"
_CHUNKS_DIR = _DATA_DIR / "chunks"
_CHECKPOINT_PATH = _DATA_DIR / "embed_checkpoint.json"
_PENDING_BATCH_PATH = _DATA_DIR / "embed_pending_batch.json"

# Match infra/environments/dev/main.tf's actual applied resource names
# (name_prefix=archibrief, environment=dev) — override via env vars if
# ever pointed at a different environment.
_VECTOR_BUCKET_NAME = os.environ.get("ARCHIBRIEF_VECTOR_BUCKET", "archibrief-dev-kb")
_VECTOR_INDEX_NAME = os.environ.get("ARCHIBRIEF_VECTOR_INDEX", "archibrief-dev-kb-index")
_REGION = os.environ.get("AWS_REGION", "us-east-1")
_MODEL_ID = "amazon.titan-embed-text-v2:0"

_MAX_WORKERS = 5  # conservative default against Bedrock per-account TPS limits
_PUT_VECTORS_BATCH_SIZE = 500  # S3 Vectors PutVectors hard limit per call
_SMOKE_TEST_WAVE_SIZE = 1  # first wave — cheap config/permissions check
_PROGRESS_EVERY = 50
_MAX_RETRIES = 5
_RETRYABLE_ERROR_CODES = {"ThrottlingException", "ServiceUnavailableException", "ModelTimeoutException"}

# A line only counts as page-furniture boilerplate (running header/footer,
# e.g. "Security Pillar AWS Well-Architected Framework" repeated near the
# top of nearly every page) if it clears BOTH gates below. Fraction alone
# would also catch a small mapping doc's individual control lines, which
# happen to repeat a handful of times across ~20 chunks for legitimate
# reasons (the same control appearing under more than one benchmark
# section) — the absolute-count floor keeps those out since the real
# per-pillar-PDF header line recurs 100-270+ times, not single digits.
_BOILERPLATE_MIN_COUNT = 15
_BOILERPLATE_MIN_FRACTION = 0.15


def _manifest() -> dict:
    return {
        "vector_bucket": _VECTOR_BUCKET_NAME,
        "index_name": _VECTOR_INDEX_NAME,
        "model_id": _MODEL_ID,
    }


def _atomic_write_json(path: Path, data: Any) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(data), encoding="utf-8")
    os.replace(temp_path, path)


def load_checkpoint() -> dict[str, str]:
    """Returns {chunk_id: embedding_hash} for chunks already embedded and
    written under the CURRENT manifest (bucket/index/model). Keyed by
    `_embedding_hash(chunk)` — embedding_input (heading + text) plus
    content_type and the parser/chunker/corpus version fields — not just
    the chunk's own `content_hash` (body text only). Two real gaps found
    via Codex review: since heading_path is prepended before embedding
    but wasn't part of the invalidation key (2026-09-14), a chunk whose
    heading_path changed while its body text stayed the same would have
    been silently skipped on resume; since content_type/version fields
    weren't part of the key either (2026-09-15), a chunk reclassified by a
    parser fix (e.g. prose -> table) with byte-identical text would have
    been silently skipped too, leaving a stale embedding paired with new
    metadata. A checkpoint written against a different target is refused,
    not silently reused — a stale checkpoint against a recreated/different
    index would otherwise make the script silently skip every chunk."""
    if not _CHECKPOINT_PATH.exists():
        return {}
    data = json.loads(_CHECKPOINT_PATH.read_text(encoding="utf-8"))
    if data.get("manifest") != _manifest():
        raise RuntimeError(
            f"{_CHECKPOINT_PATH} was written for a different target "
            f"({data.get('manifest')}) than the current one ({_manifest()}). "
            "Delete or rename the old checkpoint if this is intentional — "
            "reusing it as-is would silently skip chunks against the wrong index."
        )
    return data.get("chunks", {})


def save_checkpoint(chunk_hashes: dict[str, str]) -> None:
    _atomic_write_json(_CHECKPOINT_PATH, {"manifest": _manifest(), "chunks": chunk_hashes})


def load_all_chunks() -> list[dict]:
    chunks = []
    for path in sorted(_CHUNKS_DIR.glob("*.json")):
        chunks.extend(json.loads(path.read_text(encoding="utf-8")))
    return chunks


def embed_with_retry(embedder: BedrockEmbeddingClient, text: str) -> list[float]:
    delay = 1.0
    for attempt in range(_MAX_RETRIES):
        try:
            return embedder.embed(text)
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code", "")
            if code in _RETRYABLE_ERROR_CODES and attempt < _MAX_RETRIES - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise
    raise RuntimeError(f"embed_with_retry exhausted {_MAX_RETRIES} retries without returning or raising")


def compute_boilerplate_lines(chunks: list[dict]) -> dict[str | None, frozenset[str]]:
    """Per-document_id set of running-header/footer lines to strip before
    embedding. Real gap found 2026-09-15 (independent Codex review of q12,
    "seven areas that make up security in the cloud"): every WAF pillar
    PDF repeats its title as a running header (e.g. "Security Pillar AWS
    Well-Architected Framework") on nearly every page, so it ends up
    baked into a third or more of that document's chunks — diluting the
    genuine semantic signal Titan embeds for those chunks. See the module
    constants for why both a count and a fraction gate are required."""
    by_document: dict[str | None, list[dict]] = {}
    for chunk in chunks:
        by_document.setdefault(chunk.get("document_id"), []).append(chunk)

    boilerplate: dict[str | None, frozenset[str]] = {}
    for document_id, doc_chunks in by_document.items():
        line_counts: dict[str, int] = {}
        for chunk in doc_chunks:
            # Real gap found 2026-09-15 (Codex review): count each line at
            # most once per chunk. A malformed TOC/index chunk can repeat
            # a line (e.g. "Implementation guidance ... 8") many times
            # internally — waf-cost-optimization-pillar-0000 repeats one
            # such line 9 times by itself — which must not let 1-2
            # pathological chunks satisfy the >=15-occurrence gate on
            # their own. The numerator has to be distinct chunks to be
            # comparable with the >=15% chunk-fraction gate below.
            lines_in_chunk = {line.strip() for line in chunk["text"].split("\n") if line.strip()}
            for line in lines_in_chunk:
                line_counts[line] = line_counts.get(line, 0) + 1
        threshold = max(_BOILERPLATE_MIN_COUNT, _BOILERPLATE_MIN_FRACTION * len(doc_chunks))
        boilerplate[document_id] = frozenset(
            line for line, count in line_counts.items() if count >= threshold
        )
    return boilerplate


def _strip_boilerplate(text: str, boilerplate_lines: frozenset[str]) -> str:
    """Drops lines that exactly match a known boilerplate line for this
    chunk's document. Returns "" if that empties the text entirely — the
    caller (embedding_input) decides the fallback, since the right one
    depends on whether the chunk has a usable heading_path."""
    if not boilerplate_lines:
        return text
    kept = [line for line in text.split("\n") if line.strip() not in boilerplate_lines]
    return "\n".join(kept).strip()


def embedding_input(chunk: dict, boilerplate_lines: frozenset[str] = frozenset()) -> str:
    """What actually gets sent to Titan — heading context prepended to
    the chunk text, with per-document boilerplate lines (see
    compute_boilerplate_lines) stripped out first. Real gap found
    2026-09-14 (Codex review of the first retrieval validation,
    independently confirmed): labels like "COST01-BP01" usually live in
    the heading, not the body text, so embedding text alone made those
    chunks hard to find by their own label. The stored citation text
    (metadata["text"], via to_vector_record) is untouched — this only
    changes what the embedding model sees, not what gets cited.

    Real gap found 2026-09-15 (Codex review): a chunk whose entire body
    is nothing but a repeated boilerplate header (137 such chunks in the
    current corpus, e.g. waf-cost-optimization-pillar-0019 — a
    "COST01-BP01 Establish ownership..." Implementation guidance section
    whose body is just the running pillar-title header) used to fall back
    to the ORIGINAL unstripped text, i.e. embedding the boilerplate itself
    — even though heading_path already carries real, specific signal for
    these chunks and embedding_input prepends it anyway. Falling back to
    heading_path alone (no boilerplate, no empty body) is strictly better.
    heading_path is empty for none of the 137 real header-only chunks
    found, but a chunk with neither real body text nor heading_path would
    have nothing else to embed, so as a last resort it keeps the original
    (boilerplate-including) text — embedding boilerplate beats embedding
    nothing."""
    heading_path = chunk.get("heading_path") or []
    heading_prefix = " > ".join(heading_path)
    stripped = _strip_boilerplate(chunk["text"], boilerplate_lines)
    if not stripped:
        return heading_prefix or chunk["text"]
    if not heading_prefix:
        return stripped
    return heading_prefix + "\n\n" + stripped


def _embedding_hash(chunk: dict, boilerplate_lines: frozenset[str] = frozenset()) -> str:
    """Hash used for checkpoint invalidation — see load_checkpoint's
    docstring for why this must NOT be chunk["content_hash"] (body text
    only). Also NOT just a hash of embedding_input: a real gap found via
    Codex review 2026-09-15, on top of the earlier heading_path gap this
    function already fixed — a chunk whose parser/chunker/corpus_version
    or content_type changed (e.g. prose -> table, from a segmentation
    fix) while its heading+text stayed byte-identical would otherwise be
    silently skipped on a resumed/rerun embed, leaving a stale embedding
    paired with new metadata. content_type and the three version fields
    are included alongside embedding_input (what's actually sent to
    Titan) so any of those changing forces re-embedding even when the
    text itself didn't move."""
    payload = "\x1f".join(
        [
            embedding_input(chunk, boilerplate_lines),
            chunk.get("content_type", "prose"),
            chunk.get("parser_version", ""),
            chunk.get("chunker_version", ""),
            chunk.get("corpus_version", ""),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def to_vector_record(chunk: dict, embedding: list[float]) -> dict:
    """S3 Vectors metadata is a free-form JSON document — the whole chunk
    (minus chunk_id, which becomes the vector key) travels as metadata,
    giving every retrieved vector full citation info with no second
    lookup. `text` is one of the index's locked non-filterable keys
    (infra/modules/s3-vectors/variables.tf), so it's excluded from the
    filterable-metadata size limit. None values are stripped — AWS's
    documented metadata value types are string/number/boolean/list; null
    isn't clearly guaranteed, and some HTML-source chunks have
    source_edition=None (no dated edition to record). Empty lists are
    also stripped — confirmed live against the real index (2026-09-14):
    S3 Vectors rejects `PutVectors` outright with "Empty arrays are not
    allowed in metadata" for the 4 front-matter chunks whose
    heading_path is []."""
    metadata = {
        key: value
        for key, value in chunk.items()
        if key != "chunk_id" and value is not None and value != []
    }
    return {
        "key": chunk["chunk_id"],
        "data": {"float32": embedding},
        "metadata": metadata,
    }


def _embed_wave(
    embedder: BedrockEmbeddingClient,
    wave: list[dict],
    boilerplate_lines: dict[str | None, frozenset[str]] | None = None,
) -> list[tuple[dict, list[float]]]:
    """Embeds one bounded wave of chunks. On any failure, cancels the
    rest of the wave's queued work immediately instead of letting
    ThreadPoolExecutor's default shutdown(wait=True) run it to
    completion — see module docstring."""
    boilerplate_lines = boilerplate_lines or {}
    results: list[tuple[dict, list[float]]] = []
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {
            pool.submit(
                embed_with_retry,
                embedder,
                embedding_input(chunk, boilerplate_lines.get(chunk.get("document_id"), frozenset())),
            ): chunk
            for chunk in wave
        }
        try:
            for future in as_completed(futures):
                chunk = futures[future]
                embedding = future.result()
                results.append((chunk, embedding))
        except Exception:
            for pending in futures:
                pending.cancel()
            pool.shutdown(wait=True, cancel_futures=True)
            raise
    return results


def _replay_pending_batch_if_any(vectors_client: S3VectorsClient, chunk_hashes: dict[str, str]) -> None:
    """A pending-batch file means a previous run embedded (and paid for)
    a batch but crashed before confirming it was written + checkpointed.
    Replaying the PutVectors call is safe — S3 Vectors overwrites an
    existing vector with the same key — and avoids re-calling Bedrock for
    chunks already paid for."""
    if not _PENDING_BATCH_PATH.exists():
        return
    pending = json.loads(_PENDING_BATCH_PATH.read_text(encoding="utf-8"))
    if pending.get("manifest") != _manifest():
        raise RuntimeError(
            f"{_PENDING_BATCH_PATH} was written for a different target than the current one — "
            "resolve manually before proceeding (it represents already-paid-for embeddings)."
        )
    records = pending["records"]
    embedding_hashes = pending.get("embedding_hashes")
    if embedding_hashes is None:
        raise RuntimeError(
            f"{_PENDING_BATCH_PATH} predates embedding-hash checkpointing and can't be "
            "safely replayed automatically — delete it (the paid-for embeddings are already "
            "in this file, but confirm they made it into the index before doing so) and re-run."
        )
    print(f"Replaying {len(records)} pending vectors from a previous interrupted run...")
    vectors_client.put_vectors(records)
    chunk_hashes.update(embedding_hashes)
    save_checkpoint(chunk_hashes)
    _PENDING_BATCH_PATH.unlink()


def _write_wave(
    vectors_client: S3VectorsClient,
    wave_results: list[tuple[dict, list[float]]],
    chunk_hashes: dict[str, str],
    boilerplate_lines: dict[str | None, frozenset[str]] | None = None,
) -> None:
    boilerplate_lines = boilerplate_lines or {}
    records = [to_vector_record(chunk, embedding) for chunk, embedding in wave_results]
    embedding_hashes = {
        chunk["chunk_id"]: _embedding_hash(chunk, boilerplate_lines.get(chunk.get("document_id"), frozenset()))
        for chunk, _ in wave_results
    }
    _atomic_write_json(
        _PENDING_BATCH_PATH,
        {"manifest": _manifest(), "records": records, "embedding_hashes": embedding_hashes},
    )
    vectors_client.put_vectors(records)
    chunk_hashes.update(embedding_hashes)
    save_checkpoint(chunk_hashes)
    _PENDING_BATCH_PATH.unlink()


def _plan_waves(remaining: list[dict]) -> list[list[dict]]:
    """First wave is a single chunk (smoke test); the rest are full-size
    batches matching PutVectors' 500-item limit."""
    if not remaining:
        return []
    waves = [remaining[:_SMOKE_TEST_WAVE_SIZE]]
    cursor = _SMOKE_TEST_WAVE_SIZE
    while cursor < len(remaining):
        waves.append(remaining[cursor : cursor + _PUT_VECTORS_BATCH_SIZE])
        cursor += _PUT_VECTORS_BATCH_SIZE
    return waves


def embed_corpus() -> None:
    chunk_hashes = load_checkpoint()
    embedder = BedrockEmbeddingClient(region_name=_REGION)
    vectors_client = S3VectorsClient(
        bucket_name=_VECTOR_BUCKET_NAME, index_name=_VECTOR_INDEX_NAME, region_name=_REGION
    )

    _replay_pending_batch_if_any(vectors_client, chunk_hashes)

    all_chunks = load_all_chunks()
    boilerplate_lines = compute_boilerplate_lines(all_chunks)
    remaining = [
        c
        for c in all_chunks
        if chunk_hashes.get(c["chunk_id"])
        != _embedding_hash(c, boilerplate_lines.get(c.get("document_id"), frozenset()))
    ]
    total_remaining = len(remaining)

    if chunk_hashes:
        print(f"Resuming — {len(chunk_hashes)} chunks already embedded per checkpoint.")
    if not remaining:
        print("Nothing to do — all chunks already embedded.")
        return

    print(f"Embedding {total_remaining} chunks ({len(all_chunks)} total in corpus)...")

    start = time.monotonic()
    completed = 0

    for wave in _plan_waves(remaining):
        if not wave:
            continue
        wave_results = _embed_wave(embedder, wave, boilerplate_lines)
        _write_wave(vectors_client, wave_results, chunk_hashes, boilerplate_lines)
        completed += len(wave_results)

        elapsed = time.monotonic() - start
        rate = completed / elapsed if elapsed > 0 else 0
        eta_seconds = (total_remaining - completed) / rate if rate > 0 else 0
        if completed % _PROGRESS_EVERY < len(wave) or completed == total_remaining:
            print(
                f"{completed}/{total_remaining} chunks embedded "
                f"({completed / total_remaining:.0%}) — "
                f"elapsed {elapsed / 60:.1f}m, est. remaining {eta_seconds / 60:.1f}m",
                flush=True,
            )

    print(f"\nDone — {len(chunk_hashes)} total chunks embedded and written to S3 Vectors.")


if __name__ == "__main__":
    embed_corpus()
