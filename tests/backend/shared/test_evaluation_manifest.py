import argparse
import json

from backend.shared.evaluation_manifest import (
    attach_manifest,
    build_manifest,
    evidence_manifest,
)


def test_manifest_fingerprints_content_without_publishing_prompts_or_secrets(tmp_path):
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "source.py").write_text("PRIVATE-CODE-CANARY", encoding="utf-8")
    (backend / "build").mkdir()
    (backend / "build" / "vendor.py").write_text("vendored", encoding="utf-8")
    cases = {"dev": [{"question": "PRIVATE-PROMPT-CANARY"}]}
    result = build_manifest(cases, {"model": "test-model"}, root=tmp_path)
    assert result["source_complete"] is True
    assert result["selected_set_sizes"] == {"dev": 1}
    assert result["local_corpus_available"] is False
    assert result["live_index_verified"] is False
    assert result["git_revision"] is None
    assert list(result["file_sha256"]) == ["backend/source.py"]
    assert "PRIVATE" not in json.dumps(result)
    same = build_manifest(cases, {"model": "test-model"}, root=tmp_path)
    assert same == result
    different = build_manifest({"dev": [{"question": "changed"}]}, {}, root=tmp_path)
    assert different["selected_cases_sha256"] != result["selected_cases_sha256"]
    assert different["working_source_sha256"] == result["working_source_sha256"]
    (backend / "source.py").write_text("changed code", encoding="utf-8")
    assert (
        build_manifest(cases, {}, root=tmp_path)["working_source_sha256"]
        != result["working_source_sha256"]
    )


def test_missing_sources_and_present_corpus_are_disclosed(tmp_path):
    missing = build_manifest({}, {}, root=tmp_path)
    assert missing["source_complete"] is False
    assert missing["unavailable_files"] == ["backend"]
    chunks = tmp_path / "backend/corpus/data/chunks"
    chunks.mkdir(parents=True)
    (chunks / "corpus.json").write_text(
        '[{"text":"PRIVATE-CORPUS-CANARY"}]', encoding="utf-8"
    )
    present = build_manifest({}, {}, root=tmp_path)
    assert present["local_corpus_available"] is True
    assert len(present["corpus_files_sha256"]["corpus.json"]) == 64
    assert "PRIVATE" not in json.dumps(present)


def test_attached_manifest_records_real_contracts_without_creating_clients(monkeypatch):
    import boto3

    monkeypatch.setattr(
        boto3,
        "client",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("created AWS client")),
    )
    args = argparse.Namespace()
    attach_manifest(args, {"test": []}, {"model": "recorded-model"})
    contracts = args.evaluation_manifest["contracts"]
    assert contracts["reason_prompt"] == "reason_prompt@2026-10-29"
    assert contracts["chat_prompt"] == "chat_prompt@2026-10-23b"
    assert len(contracts["finding_schema_sha256"]) == 64


def test_evidence_identity_excludes_text_urls_and_bounds_omission():
    chunk = {
        "chunk_id": "chunk-a",
        "document_id": "doc-a",
        "corpus_version": "corpus@1",
        "parser_version": "parser-v1",
        "content_hash": "a" * 64,
        "retrieved_at": "2026-10-24T00:00:00Z",
        "text": "PRIVATE-TEXT-CANARY",
        "source_url": "https://example.com/?token=PRIVATE-URL-CANARY",
    }
    result = evidence_manifest([chunk] * 70)
    assert result["count"] == 70 and result["omitted"] == 6
    assert len(result["chunks"]) == 64
    assert result["source_content_verified"] is False
    assert result["chunks"][0]["content_hash"] == "a" * 64
    assert "PRIVATE" not in json.dumps(result)
