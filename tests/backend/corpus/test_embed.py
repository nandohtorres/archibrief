import io
import json

import pytest
from botocore.exceptions import ClientError
from botocore.response import StreamingBody
from botocore.stub import Stubber

from backend.corpus import embed
from backend.shared.clients import BedrockEmbeddingClient, S3VectorsClient


def _invoke_model_response(embedding: list[float]) -> dict:
    body = json.dumps({"embedding": embedding, "inputTextTokenCount": 5}).encode("utf-8")
    return {"body": StreamingBody(io.BytesIO(body), len(body)), "contentType": "application/json"}


def _chunk(chunk_id: str, text: str = "some text", content_hash: str = "hash1", **extra) -> dict:
    base = {"chunk_id": chunk_id, "text": text, "content_hash": content_hash}
    base.update(extra)
    return base


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(embed, "_CHECKPOINT_PATH", tmp_path / "embed_checkpoint.json")
    monkeypatch.setattr(embed, "_PENDING_BATCH_PATH", tmp_path / "embed_pending_batch.json")
    yield


def test_checkpoint_roundtrip():
    assert embed.load_checkpoint() == {}
    embed.save_checkpoint({"a-0001": "hash1", "a-0002": "hash2"})
    assert embed.load_checkpoint() == {"a-0001": "hash1", "a-0002": "hash2"}


def test_checkpoint_refuses_a_different_targets_checkpoint(monkeypatch):
    embed.save_checkpoint({"a-0001": "hash1"})
    monkeypatch.setattr(embed, "_VECTOR_INDEX_NAME", "some-other-index")
    with pytest.raises(RuntimeError, match="different target"):
        embed.load_checkpoint()


def test_to_vector_record_excludes_chunk_id_none_values_and_empty_lists():
    chunk = _chunk(
        "iam-best-practices-0003",
        source_edition=None,
        license="CC-BY-SA-4.0",
        heading_path=[],
    )
    record = embed.to_vector_record(chunk, embedding=[0.1, 0.2, 0.3])

    assert record["key"] == "iam-best-practices-0003"
    assert record["data"] == {"float32": [0.1, 0.2, 0.3]}
    assert "chunk_id" not in record["metadata"]
    assert "source_edition" not in record["metadata"]
    assert "heading_path" not in record["metadata"]
    assert record["metadata"]["license"] == "CC-BY-SA-4.0"


def test_to_vector_record_keeps_a_non_empty_list():
    chunk = _chunk("c-0000", heading_path=["Security foundations"])
    record = embed.to_vector_record(chunk, embedding=[0.1])
    assert record["metadata"]["heading_path"] == ["Security foundations"]


def test_embedding_input_prepends_heading_path():
    chunk = _chunk("c-0000", text="Establish ownership.", heading_path=["Practice Cloud Financial Management", "COST01-BP01"])
    assert embed.embedding_input(chunk) == "Practice Cloud Financial Management > COST01-BP01\n\nEstablish ownership."


def test_embedding_input_falls_back_to_bare_text_when_no_heading_path():
    chunk = _chunk("c-0000", text="View a markdown version of this page", heading_path=[])
    assert embed.embedding_input(chunk) == "View a markdown version of this page"


def test_embedding_input_strips_boilerplate_lines():
    chunk = _chunk(
        "c-0000",
        text="Security Pillar AWS Well-Architected Framework\nReal content about SEC01.",
        heading_path=["Security foundations"],
    )
    boilerplate_lines = frozenset({"Security Pillar AWS Well-Architected Framework"})
    assert embed.embedding_input(chunk, boilerplate_lines) == (
        "Security foundations\n\nReal content about SEC01."
    )


def test_embedding_input_keeps_full_text_when_stripping_would_empty_it_and_no_heading_path():
    """True last-resort edge case: no heading_path AND stripping would
    empty the body. In the real 4463-chunk corpus this never happens —
    every one of the 137
    real header-only chunks has a non-empty heading_path — but embedding
    boilerplate is still better than embedding nothing if it ever does."""
    chunk = _chunk(
        "c-0000",
        text="Security Pillar AWS Well-Architected Framework",
        heading_path=[],
    )
    boilerplate_lines = frozenset({"Security Pillar AWS Well-Architected Framework"})
    assert embed.embedding_input(chunk, boilerplate_lines) == (
        "Security Pillar AWS Well-Architected Framework"
    )


def test_embedding_input_uses_heading_path_only_when_stripping_would_empty_a_header_only_chunk():
    """A chunk whose entire body is just the repeated pillar-title header
    must not fall back to the ORIGINAL unstripped (boilerplate-including)
    text. Real example from
    the current corpus: waf-cost-optimization-pillar-0019, body is only
    "Cost Optimization Pillar AWS Well-Architected Framework", with
    heading_path ['Practice Cloud Financial Management', 'COST01-BP01
    Establish ownership of cost optimization', 'Implementation
    guidance'] — heading_path alone already carries real signal, so the
    fallback should use ONLY that, not the boilerplate header."""
    chunk = _chunk(
        "waf-cost-optimization-pillar-0019",
        text="Cost Optimization Pillar AWS Well-Architected Framework",
        heading_path=[
            "Practice Cloud Financial Management",
            "COST01-BP01 Establish ownership of cost optimization",
            "Implementation guidance",
        ],
    )
    boilerplate_lines = frozenset({"Cost Optimization Pillar AWS Well-Architected Framework"})
    assert embed.embedding_input(chunk, boilerplate_lines) == (
        "Practice Cloud Financial Management > COST01-BP01 Establish ownership of cost optimization > Implementation guidance"
    )


def test_compute_boilerplate_lines_flags_a_running_header_repeated_across_a_document():
    """Real boilerplate found empirically in backend/corpus/data/chunks/
    waf-security-pillar.json: "Security Pillar AWS
    Well-Architected Framework" recurs verbatim in 238/701 chunks — a
    running page header, not semantic content."""
    doc_id = "waf-security-pillar"
    header = "Security Pillar AWS Well-Architected Framework"
    chunks = [_chunk(f"{doc_id}-{i:04d}", text=f"{header}\nSEC01-BP0{i} guidance body text.", document_id=doc_id) for i in range(20)]
    chunks.append(_chunk(f"{doc_id}-0020", text="No header here, just body text.", document_id=doc_id))

    boilerplate = embed.compute_boilerplate_lines(chunks)

    assert header in boilerplate[doc_id]


def test_compute_boilerplate_lines_does_not_flag_a_line_repeated_only_a_handful_of_times():
    """Regression guard: a small mapping doc can have the same control
    description line recur a handful of times for legitimate reasons
    (real content, not page furniture) — the count floor must keep this
    out even though the fraction gate alone would catch it."""
    doc_id = "aws-cis-foundations-mapping"
    control_line = "[CloudTrail.1] CloudTrail should be enabled and configured"
    chunks = [_chunk(f"{doc_id}-{i:04d}", text=f"{control_line}\nMapping detail {i}.", document_id=doc_id) for i in range(4)]
    chunks.extend(_chunk(f"{doc_id}-{i:04d}", text=f"Unrelated body text {i}.", document_id=doc_id) for i in range(4, 23))

    boilerplate = embed.compute_boilerplate_lines(chunks)

    assert control_line not in boilerplate[doc_id]


def test_compute_boilerplate_lines_counts_a_line_at_most_once_per_chunk():
    """Counting must be by distinct chunks, not raw line occurrences, or a
    line repeated many times WITHIN a single pathological chunk inflates
    the count as if it were genuinely document-wide. Real example from
    the current corpus:
    waf-cost-optimization-pillar-0000 (a malformed table-of-contents
    chunk) repeats the line "Implementation guidance ... 8" 9 times by
    itself. Here that TOC-style line appears 16 times raw, clearing the
    raw >=15-occurrence gate the old (buggy) code used, but in only 2
    distinct chunks out of 20 -- well below the 15-distinct-chunk floor
    once deduped -- so it must NOT be flagged."""
    doc_id = "waf-cost-optimization-pillar"
    toc_line = "Implementation guidance ..................................................................................................................... 8"
    chunks = [
        _chunk(f"{doc_id}-0000", text="\n".join([toc_line] * 9), document_id=doc_id),
        _chunk(f"{doc_id}-0001", text="\n".join([toc_line] * 7), document_id=doc_id),
    ]
    chunks.extend(_chunk(f"{doc_id}-{i:04d}", text=f"Unrelated body text {i}.", document_id=doc_id) for i in range(2, 20))

    boilerplate = embed.compute_boilerplate_lines(chunks)

    assert toc_line not in boilerplate[doc_id]


def test_compute_boilerplate_lines_does_not_flag_a_structural_subheading():
    """"Resources"/"Implementation guidance" recur across a document too,
    but far less often than a running page header (roughly one per best
    practice section vs. one per page) — must stay below the threshold."""
    doc_id = "waf-cost-optimization-pillar"
    chunks = []
    for i in range(100):
        text = "Resources\nSome best-practice-specific body text." if i % 10 == 0 else f"Body text {i}."
        chunks.append(_chunk(f"{doc_id}-{i:04d}", text=text, document_id=doc_id))

    boilerplate = embed.compute_boilerplate_lines(chunks)

    assert "Resources" not in boilerplate[doc_id]


def test_embed_wave_strips_boilerplate_lines_via_embedding_input(monkeypatch):
    captured_texts = []

    def fake_embed(_embedder, text):
        captured_texts.append(text)
        return [0.0]

    monkeypatch.setattr(embed, "embed_with_retry", fake_embed)
    chunk = _chunk(
        "waf-security-pillar-0006",
        text="Security Pillar AWS Well-Architected Framework\nReal content.",
        document_id="waf-security-pillar",
        heading_path=[],
    )
    boilerplate_lines = {"waf-security-pillar": frozenset({"Security Pillar AWS Well-Architected Framework"})}

    embed._embed_wave(embedder=object(), wave=[chunk], boilerplate_lines=boilerplate_lines)

    assert captured_texts == ["Real content."]


def test_embed_with_retry_retries_on_throttling_then_succeeds(monkeypatch):
    monkeypatch.setattr(embed.time, "sleep", lambda _seconds: None)
    client = BedrockEmbeddingClient(region_name="us-east-1")
    stubber = Stubber(client._client)
    stubber.add_client_error("invoke_model", service_error_code="ThrottlingException")
    stubber.add_response("invoke_model", _invoke_model_response([0.1, 0.2]))
    stubber.activate()

    result = embed.embed_with_retry(client, "some chunk text")

    assert result == [0.1, 0.2]
    stubber.assert_no_pending_responses()


def test_embed_with_retry_raises_immediately_on_non_retryable_error():
    client = BedrockEmbeddingClient(region_name="us-east-1")
    stubber = Stubber(client._client)
    stubber.add_client_error("invoke_model", service_error_code="ValidationException")
    stubber.activate()

    with pytest.raises(ClientError):
        embed.embed_with_retry(client, "some chunk text")


def test_plan_waves_uses_a_single_chunk_smoke_test_wave_first():
    chunks = [_chunk(f"c-{i:04d}") for i in range(1201)]
    waves = embed._plan_waves(chunks)

    assert len(waves[0]) == 1
    assert len(waves[1]) == 500
    assert len(waves[2]) == 500
    assert len(waves[3]) == 200
    assert sum(len(w) for w in waves) == 1201


def test_plan_waves_returns_empty_list_for_no_remaining_chunks():
    assert embed._plan_waves([]) == []


def test_embed_wave_stops_and_cancels_on_failure(monkeypatch):
    call_count = {"n": 0}

    def fake_embed(_embedder, _text):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise ValueError("simulated failure")
        return [0.0]

    monkeypatch.setattr(embed, "embed_with_retry", fake_embed)
    wave = [_chunk(f"c-{i:04d}") for i in range(5)]

    with pytest.raises(ValueError, match="simulated failure"):
        embed._embed_wave(embedder=object(), wave=wave)


def test_write_wave_persists_pending_batch_then_clears_it_and_updates_checkpoint():
    chunk = _chunk("c-0000", text="t", content_hash="h0")
    expected_embedding_hash = embed._embedding_hash(chunk)

    vectors_client = S3VectorsClient(bucket_name="bkt", index_name="idx", region_name="us-east-1")
    stubber = Stubber(vectors_client._client)
    stubber.add_response(
        "put_vectors",
        {},
        {
            "vectorBucketName": "bkt",
            "indexName": "idx",
            "vectors": [
                {"key": "c-0000", "data": {"float32": [0.1]}, "metadata": {"text": "t", "content_hash": "h0"}}
            ],
        },
    )
    stubber.activate()

    chunk_hashes: dict[str, str] = {}

    embed._write_wave(vectors_client, [(chunk, [0.1])], chunk_hashes)

    stubber.assert_no_pending_responses()
    assert not embed._PENDING_BATCH_PATH.exists()
    assert chunk_hashes == {"c-0000": expected_embedding_hash}
    assert embed.load_checkpoint() == {"c-0000": expected_embedding_hash}


def test_write_wave_invalidates_checkpoint_when_only_heading_path_changes():
    """heading_path is prepended before embedding, so a checkpoint keyed
    by content_hash (body text only) would silently skip a chunk whose
    heading changed while its body stayed the same, leaving a stale
    embedding on resume."""
    chunk_before = _chunk("c-0000", text="t", content_hash="h0", heading_path=["A"])
    chunk_after = _chunk("c-0000", text="t", content_hash="h0", heading_path=["B"])
    assert embed._embedding_hash(chunk_before) != embed._embedding_hash(chunk_after)


def test_replay_pending_batch_writes_it_and_updates_checkpoint():
    pending = {
        "manifest": embed._manifest(),
        "records": [
            {"key": "c-0000", "data": {"float32": [0.1]}, "metadata": {"text": "t", "content_hash": "h0"}}
        ],
        "embedding_hashes": {"c-0000": "eh0"},
    }
    embed._PENDING_BATCH_PATH.write_text(json.dumps(pending), encoding="utf-8")

    vectors_client = S3VectorsClient(bucket_name="bkt", index_name="idx", region_name="us-east-1")
    stubber = Stubber(vectors_client._client)
    stubber.add_response("put_vectors", {}, {"vectorBucketName": "bkt", "indexName": "idx", "vectors": pending["records"]})
    stubber.activate()

    chunk_hashes: dict[str, str] = {}
    embed._replay_pending_batch_if_any(vectors_client, chunk_hashes)

    stubber.assert_no_pending_responses()
    assert not embed._PENDING_BATCH_PATH.exists()
    assert chunk_hashes == {"c-0000": "eh0"}
    assert embed.load_checkpoint() == {"c-0000": "eh0"}


def test_replay_pending_batch_refuses_a_pending_file_without_embedding_hashes():
    """A pending-batch file from before embedding-hash checkpointing
    can't be safely replayed automatically — fail loudly rather than
    guessing or silently skipping the checkpoint update."""
    pending = {
        "manifest": embed._manifest(),
        "records": [{"key": "c-0000", "data": {"float32": [0.1]}, "metadata": {"text": "t"}}],
    }
    embed._PENDING_BATCH_PATH.write_text(json.dumps(pending), encoding="utf-8")

    vectors_client = S3VectorsClient(bucket_name="bkt", index_name="idx", region_name="us-east-1")
    with pytest.raises(RuntimeError, match="predates embedding-hash checkpointing"):
        embed._replay_pending_batch_if_any(vectors_client, {})


def test_replay_pending_batch_does_nothing_when_no_file_exists():
    vectors_client = S3VectorsClient(bucket_name="bkt", index_name="idx", region_name="us-east-1")
    embed._replay_pending_batch_if_any(vectors_client, {})  # must not raise / not call AWS


def test_replay_pending_batch_refuses_a_mismatched_manifest():
    pending = {"manifest": {**embed._manifest(), "index_name": "other"}, "records": []}
    embed._PENDING_BATCH_PATH.write_text(json.dumps(pending), encoding="utf-8")

    vectors_client = S3VectorsClient(bucket_name="bkt", index_name="idx", region_name="us-east-1")
    with pytest.raises(RuntimeError, match="different target"):
        embed._replay_pending_batch_if_any(vectors_client, {})


def test_embed_corpus_skips_chunks_whose_content_hash_is_already_checkpointed(tmp_path, monkeypatch):
    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    already_done = _chunk("doc-0000", text="already done", content_hash="h0")
    needs_embedding = _chunk("doc-0001", text="needs embedding", content_hash="h1")
    (chunks_dir / "doc.json").write_text(
        json.dumps([already_done, needs_embedding]),
        encoding="utf-8",
    )
    monkeypatch.setattr(embed, "_CHUNKS_DIR", chunks_dir)
    already_done_hash = embed._embedding_hash(already_done)
    needs_embedding_hash = embed._embedding_hash(needs_embedding)
    embed.save_checkpoint({"doc-0000": already_done_hash})

    bedrock_client = BedrockEmbeddingClient(region_name="us-east-1")
    bedrock_stubber = Stubber(bedrock_client._client)
    bedrock_stubber.add_response("invoke_model", _invoke_model_response([0.5, 0.6]))
    bedrock_stubber.activate()

    vectors_client = S3VectorsClient(bucket_name="test-bucket", index_name="test-index", region_name="us-east-1")
    vectors_stubber = Stubber(vectors_client._client)
    vectors_stubber.add_response(
        "put_vectors",
        {},
        {
            "vectorBucketName": "test-bucket",
            "indexName": "test-index",
            "vectors": [
                {"key": "doc-0001", "data": {"float32": [0.5, 0.6]}, "metadata": {"text": "needs embedding", "content_hash": "h1"}}
            ],
        },
    )
    vectors_stubber.activate()

    monkeypatch.setattr(embed, "BedrockEmbeddingClient", lambda region_name: bedrock_client)
    monkeypatch.setattr(embed, "S3VectorsClient", lambda bucket_name, index_name, region_name: vectors_client)

    embed.embed_corpus()

    bedrock_stubber.assert_no_pending_responses()
    vectors_stubber.assert_no_pending_responses()
    assert embed.load_checkpoint() == {"doc-0000": already_done_hash, "doc-0001": needs_embedding_hash}


def test_embed_corpus_re_embeds_a_chunk_whose_text_changed_under_the_same_id(tmp_path, monkeypatch):
    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    new_chunk = _chunk("doc-0000", text="new text", content_hash="h_new")
    (chunks_dir / "doc.json").write_text(
        json.dumps([new_chunk]),
        encoding="utf-8",
    )
    monkeypatch.setattr(embed, "_CHUNKS_DIR", chunks_dir)
    new_embedding_hash = embed._embedding_hash(new_chunk)
    embed.save_checkpoint({"doc-0000": "stale_hash_from_before_the_text_changed"})

    bedrock_client = BedrockEmbeddingClient(region_name="us-east-1")
    bedrock_stubber = Stubber(bedrock_client._client)
    bedrock_stubber.add_response("invoke_model", _invoke_model_response([0.9]))
    bedrock_stubber.activate()

    vectors_client = S3VectorsClient(bucket_name="test-bucket", index_name="test-index", region_name="us-east-1")
    vectors_stubber = Stubber(vectors_client._client)
    vectors_stubber.add_response(
        "put_vectors",
        {},
        {
            "vectorBucketName": "test-bucket",
            "indexName": "test-index",
            "vectors": [{"key": "doc-0000", "data": {"float32": [0.9]}, "metadata": {"text": "new text", "content_hash": "h_new"}}],
        },
    )
    vectors_stubber.activate()

    monkeypatch.setattr(embed, "BedrockEmbeddingClient", lambda region_name: bedrock_client)
    monkeypatch.setattr(embed, "S3VectorsClient", lambda bucket_name, index_name, region_name: vectors_client)

    embed.embed_corpus()

    bedrock_stubber.assert_no_pending_responses()
    vectors_stubber.assert_no_pending_responses()
    assert embed.load_checkpoint() == {"doc-0000": new_embedding_hash}
