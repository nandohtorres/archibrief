---
title: "ADR 0036: Structure-Aware Chunking Baseline"
type: decision
tags: [adr, project, work-project, archibrief]
created: "2026-09-03"
updated: "2026-09-03"
status: accepted
---

# ADR 0036: Structure-Aware Chunking Baseline

**Status:** Accepted (2026-09-03) — **extends/corrects** ADR-0020's
overgeneralized claim; incremental ingestion approach stands

## Context

Codex flagged that ADR-0020's "512-token recursive splitting always beats
semantic chunking" was an overgeneralization from one external benchmark
— AWS's own Bedrock Knowledge Bases documentation recommends splitting
Titan inputs into logical paragraphs/sections and supports fixed,
hierarchical, and semantic strategies specifically because structure
matters for well-formatted technical documentation like AWS's own docs.

## Decision

Baseline chunking approach, provisional pending ArchiBrief's own
retrieval evaluation set:

- normalize each source into a versioned document snapshot;
- split first on document heading/section boundaries, preserving
  headings with body text;
- keep tables, warnings, ordered procedures, and code blocks intact
  where possible;
- apply the 512-token recursive fallback only inside oversized sections
  that don't have clean structural boundaries;
- compare 256/512/1,024-token variants and overlap values on
  ArchiBrief's own questions once an eval set exists (same set used for
  ADR-0035's embedding-model evaluation);
- treat exact AWS identifiers/control names with a deterministic/lexical
  companion lookup where vector recall alone might miss them;
- handle additions, changes, deletions, renames, and source-version
  replacement in incremental sync using content hashes.

Metadata per chunk expands beyond source/section/timestamp: source
edition/retrieved-at date, canonical URL, document and chunk IDs, content
hash, heading path, exact text span, parser/chunker version, corpus
version — this is what makes ADR-0002/ADR-0027's citation-reproducibility
contract actually work.

## Consequences

- More metadata fields than originally scoped in
  [[Work-Project-System-Design]]'s S3 Vectors structure — update that doc
  accordingly.

## Full reasoning

See [[Work-Project-ADR-Review-Codex]] §"ADR-0020."
