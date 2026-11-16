import { publicUnverified } from "./unverified";
import type { ChatTurn, FindingType, ReportFinding, ReviewReport } from "./contracts";
import type { DemoEntry, ReviewerNote } from "./demos";
import { assessmentFor } from "./assessment";
import { PRESENTATION_VERSION, briefCardFor, tierFor } from "./stakeholder-brief";
import {
  MONEY_POLICY_VERSION,
  PUBLIC_POLICY_NOTE,
  publicRecord,
  publicTurn,
} from "./public-projection";

// These labels describe evidence provenance, not severity. Keep historical
// priority keys compatible for historical clients; risk uses assessment.ts.
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
    const recorded = [...new Set(findings.map(({ record }) => record[field]).filter(Boolean))]
      .map(String)
      .filter((value) => value !== "unknown");
    // "rule_engine@x+trivy@y" already names "rule_engine@x"; list each engine once.
    const values = recorded.filter(
      (value) => !recorded.some((other) => other !== value && other.startsWith(`${value}+`)),
    );
    return values.length ? values.sort().join(", ") : "not recorded";
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

type ExportedFinding = Omit<ReportFinding, "stakeholder"> & {
  stakeholder?: Pick<
    NonNullable<ReportFinding["stakeholder"]>,
    "source" | "concern" | "subject" | "severity" | "needs_action"
  >;
};

export function buildReportExport(
  report: ReviewReport,
  transcript: ChatTurn[],
  demo?: DemoEntry | null,
) {
  // A public copy (ADR-0062): price blocks from older backends (`budget`,
  // and the price, effort and cost-of-inaction fields on legacy stakeholder
  // cards) are left out, and cost figures in generated text are removed
  // field by field. IDs, severity, assessments and citation anchors are
  // kept; every change is listed under public_text_policy.
  const { budget: _budget, ...rest } = report;
  void _budget;
  const changedByFinding: Record<string, string[]> = {};
  const findings = report.findings.map((finding): ExportedFinding => {
    const { stakeholder, ...kept } = finding;
    const { record, changed } = publicRecord(finding.record);
    if (changed.length) changedByFinding[record.finding_id] = changed;
    const exported = { ...kept, record };
    if (!stakeholder) return exported;
    const { source, concern, subject, severity, needs_action } = stakeholder;
    return { ...exported, stakeholder: { source, concern, subject, severity, needs_action } };
  });
  let amountsInChat = 0;
  let quotesOmitted = 0;
  const chat = transcript.map((saved) => {
    const { turn, omitted } = publicTurn(saved);
    amountsInChat += turn.answer.reduce((sum, p) => sum + (p.amounts_removed ?? 0), 0);
    quotesOmitted += omitted + (saved.narrative_policy?.quotes_omitted ?? 0);
    return turn;
  });
  return {
    ...rest,
    unverified_findings: publicUnverified(report.unverified_findings),
    findings,
    public_text_policy: {
      version: MONEY_POLICY_VERSION,
      note: PUBLIC_POLICY_NOTE,
      findings_changed: changedByFinding,
      chat_amounts_removed: amountsInChat,
      chat_quotes_omitted: quotesOmitted,
    },
    stakeholder_brief: {
      presentation: PRESENTATION_VERSION,
      findings: Object.fromEntries(
        report.findings.map((finding) => {
          const card = briefCardFor(finding);
          return [
            finding.record.finding_id,
            {
              kind: card.kind,
              concern: card.kind === "curated" ? card.concern : null,
              tier: tierFor(card),
            },
          ];
        }),
      ),
    },
    assessment_view: Object.fromEntries(
      report.findings.map((finding) => [finding.record.finding_id, assessmentFor(finding)]),
    ),
    chat_transcript: chat,
    ...(demo ? { demo_review: demoReviewMetadata(demo) } : {}),
  };
}
