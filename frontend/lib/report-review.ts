import type { ChatTurn, FindingType, ReportFinding, ReviewReport } from "./contracts";
import type { DemoEntry, ReviewerNote } from "./demos";

// These labels describe evidence provenance, not severity. Keep historical
// priority keys compatible until the severity contract is separately reviewed.
export function evidenceLabel(type: FindingType): string {
  switch (type) {
    case "deterministic-rule-result":
      return "Rule result";
    case "fact":
      return "Reported fact";
    case "not-observable":
      return "Not observable";
    default:
      return "Review";
  }
}

export function withEvidenceLabel(finding: ReportFinding): ReportFinding {
  return {
    ...finding,
    presentation: { ...finding.presentation, short_label: evidenceLabel(finding.record.type) },
  };
}

export function reportSnapshotLabel(findings: ReportFinding[]): string {
  function versions(field: "deterministic_rule_version" | "corpus_version" | "prompt_version") {
    const values = [...new Set(findings.map(({ record }) => record[field]).filter(Boolean))].sort();
    return values.length ? values.join(", ") : "not recorded";
  }
  return `Snapshot · rules ${versions("deterministic_rule_version")} · corpus ${versions("corpus_version")} · prompt ${versions("prompt_version")} · static review only`;
}

export function notesForTurn(turn: ChatTurn, notes: ReviewerNote[]): ReviewerNote[] {
  const cited = new Set(
    turn.answer.flatMap((paragraph) =>
      paragraph.citations.flatMap((citation) =>
        citation.kind === "finding" ? [citation.finding_id] : [],
      ),
    ),
  );
  return notes.filter((note) => cited.has(note.findingId));
}

export function demoReviewMetadata(demo: DemoEntry) {
  return {
    schema_version: "demo-review@1",
    demo_id: demo.id,
    source: demo.source,
    source_url: demo.sourceUrl,
    license: demo.license,
    disclaimer: demo.disclaimer,
    // Historical annotations did not record their review date. Do not
    // manufacture one from today's download or implementation date.
    reviewed_at: null,
    reviewer_notes: demo.reviewerNotes ?? [],
    note: "Original generated findings and saved answers are preserved. Reviewer notes qualify or correct them; citation presence does not establish correctness.",
  };
}

export function buildReportExport(
  report: ReviewReport,
  transcript: ChatTurn[],
  demo?: DemoEntry | null,
) {
  return {
    ...report,
    chat_transcript: transcript,
    ...(demo ? { demo_review: demoReviewMetadata(demo) } : {}),
  };
}
