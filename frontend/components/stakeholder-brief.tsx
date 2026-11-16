// Stakeholder Brief (ADR-0062): the business view of the same review.
// Most serious first, one expandable row per finding. No prices: each
// row carries a qualitative commitment tier from lib/stakeholder-brief.ts.

import { useEffect, useRef, useState } from "react";
import type { ReportFinding, ReviewReport, Severity } from "@/lib/contracts";
import type { ReviewerNote } from "@/lib/demos";
import { assessmentFor } from "@/lib/assessment";
import {
  EVIDENCE_STATE_LABELS,
  MONEY_NOTE,
  SAFETY_SENTENCE,
  SOURCE_LABELS,
  TIER_EXPLANATIONS,
  TIER_LABELS,
  TIER_LEGEND,
  briefCoverage,
  buildBrief,
  evidenceStateFor,
  cardTitle,
  protectionJobs,
  tierFor,
  withoutMoney,
  type BriefRow,
  type Tier,
} from "@/lib/stakeholder-brief";
import { confidenceLabel, formatFindingId, workloadName } from "@/lib/workflow";
import { BriefScene } from "./brief-scene";
import { independentCheckLabel } from "@/lib/analysis-quality";

interface StakeholderBriefProps {
  report: ReviewReport;
  onOpenTechnicalFinding: (findingId: string) => void;
  onAsk: (finding: ReportFinding) => void;
  reviewerNotes?: Map<string, ReviewerNote>;
  // True when the page shows a real title (a demo's) above this view.
  titled?: boolean;
}

const SEVERITY_BARS: Record<Severity, number> = { critical: 4, high: 3, medium: 2, low: 1 };

function severityWord(finding: ReportFinding): { word: string; bars: number; key: string } {
  const assessment = assessmentFor(finding);
  if (assessment.action === "none") return { word: "No action proposed", bars: 0, key: "none" };
  if (!assessment.severity) return { word: "Needs confirmation", bars: 0, key: "unknown" };
  const word = assessment.severity[0].toUpperCase() + assessment.severity.slice(1);
  return { word, bars: SEVERITY_BARS[assessment.severity], key: assessment.severity };
}

function SeverityMark({ finding }: { finding: ReportFinding }) {
  const { word, bars, key } = severityWord(finding);
  return (
    <span className={`brief-severity severity-${key}`}>
      <span className="brief-bars" aria-hidden="true">
        {[1, 2, 3, 4].map((bar) => (
          <span key={bar} className={bar <= bars ? "on" : undefined} />
        ))}
      </span>
      {word}
    </span>
  );
}

function TierChip({ tier }: { tier: Tier | null }) {
  return (
    <span className={`brief-tier tier-${tier ?? "unclassified"}`}>
      {tier ? TIER_LABELS[tier] : "Unclassified"}
    </span>
  );
}

export function originalReviewDate(report: ReviewReport): string {
  const date = new Date(report.created_at);
  return Number.isNaN(date.getTime())
    ? "an unrecorded date"
    : date.toLocaleDateString("en-US", {
        year: "numeric",
        month: "long",
        day: "numeric",
        timeZone: "UTC",
      });
}

function BriefFinding({
  row,
  open,
  reviewerNote,
  onOpenTechnicalFinding,
  onAsk,
}: {
  row: BriefRow;
  open: boolean;
  reviewerNote: ReviewerNote | null;
  onOpenTechnicalFinding: (findingId: string) => void;
  onAsk: (finding: ReportFinding) => void;
}) {
  const { finding, card } = row;
  const tier = tierFor(card);
  const technical = withoutMoney(finding.record.finding);
  const moneyRemoved = technical.removed || (card.kind !== "curated" && card.moneyRemoved);
  const sections: Array<[string, string]> =
    card.kind === "curated"
      ? [
          ["Risk", card.entry.risk],
          ["Work proposed", card.entry.work],
          ["Helps prevent", card.entry.prevents],
          ["Still exposed", card.entry.stillExposed],
        ]
      : card.kind === "summary"
        ? [
            ["Risk", card.summary],
            ["Work proposed", card.action],
            ["Helps prevent", "Not stated in this summary. Check the technical evidence."],
            ["Still exposed", "Not stated in this summary. Check the technical evidence."],
          ]
        : [
            ["Risk", card.risk],
            ["Work proposed", card.action],
            ["Helps prevent", "Not stated for this finding."],
            ["Still exposed", "Not stated for this finding."],
          ];
  const sourceLabel =
    card.kind === "curated"
      ? SOURCE_LABELS.curated
      : card.kind === "summary"
        ? SOURCE_LABELS[card.writtenBy]
        : card.notObservable
          ? SOURCE_LABELS.notObservable
          : SOURCE_LABELS.technical;
  const subject = card.kind === "curated" ? card.subject : null;
  return (
    <details open={open} id={`brief-${finding.record.finding_id}`} className="brief-row">
      <summary>
        <SeverityMark finding={finding} />
        <span className="brief-row-title">
          <small>
            {formatFindingId(finding.record.finding_id)}
            {subject && ` · ${subject}`}
          </small>
          <strong>{cardTitle(card)}</strong>
        </span>
        <span className="brief-row-tags">
          <TierChip tier={tier} />
          {reviewerNote && <span className="brief-note-badge">Reviewer correction</span>}
        </span>
        <i aria-hidden="true">›</i>
      </summary>
      <div className="brief-row-body">
        {independentCheckLabel(finding) && <p>{independentCheckLabel(finding)}</p>}
        {reviewerNote && (
          <aside className="reviewer-note" aria-label="Reviewer correction">
            <strong>Reviewer correction · {reviewerNote.verdict}</strong>
            <p>{reviewerNote.note}</p>
          </aside>
        )}
        <p className="brief-source">
          {card.kind === "summary" && (
            <strong>
              {card.writtenBy === "model"
                ? "AI-written plain summary. "
                : "Hand-written plain summary. "}
            </strong>
          )}
          {sourceLabel}
        </p>
        {card.kind === "curated" && card.entry.analogy && (
          <div className="plain-terms">
            <h4>In farm terms</h4>
            <p>{card.entry.analogy}</p>
            {card.entry.scene && <BriefScene scene={card.entry.scene} />}
          </div>
        )}
        {card.kind === "curated" && (
          <p className="brief-evidence-state">
            <strong>What the evidence shows:</strong>{" "}
            {EVIDENCE_STATE_LABELS[evidenceStateFor(card.concern)]}{" "}
            <span className="brief-principle">{card.entry.principle}</span>
          </p>
        )}
        <dl className="brief-sections">
          {sections.map(([label, text]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{text}</dd>
            </div>
          ))}
        </dl>
        <div className="brief-commitment">
          <h4>
            Typical commitment: <TierChip tier={tier} />
          </h4>
          <p>
            {tier
              ? TIER_EXPLANATIONS[tier]
              : "Unclassified: there is no typical commitment for this kind of finding. Someone who knows the system needs to scope it."}
          </p>
          {card.kind === "curated" && card.entry.biggerIf && (
            <p>
              <strong>Bigger if</strong> {card.entry.biggerIf}
            </p>
          )}
          <p className="brief-legend-inline">{TIER_LEGEND}</p>
        </div>
        {moneyRemoved && <p className="brief-money-note">{MONEY_NOTE}</p>}
        <p className="card-technical">
          <strong>Technical finding:</strong> {technical.text}
        </p>
        <p className="plain-confidence">
          <strong>Evidence confidence: {confidenceLabel(finding.record.confidence)}.</strong> How
          direct the evidence is. It doesn&apos;t measure whether the finding is right.
        </p>
        <div className="guided-actions">
          <button
            className="button secondary"
            type="button"
            onClick={() => onOpenTechnicalFinding(finding.record.finding_id)}
          >
            View technical evidence
          </button>
          <button className="button secondary" type="button" onClick={() => onAsk(finding)}>
            Ask about this finding
          </button>
        </div>
      </div>
    </details>
  );
}

function introText(report: ReviewReport, model: ReturnType<typeof buildBrief>): string {
  const counts = (["critical", "high", "medium", "low"] as Severity[])
    .filter((s) => model.severityCounts[s] > 0)
    .map((s) => `${model.severityCounts[s]} ${s}`);
  if (model.unassessedCount) counts.push(`${model.unassessedCount} needing confirmation`);
  const total = model.rows.length;
  const lead =
    total === 0
      ? "No finding in this review needs a decision. That is not a safety guarantee."
      : `${total} ${total === 1 ? "finding needs" : "findings need"} a decision (${counts.join(", ")}), most serious first.`;
  return `${lead} This is a plain-language reading of the review from ${originalReviewDate(report)}, not a new review: the evidence and finding IDs are unchanged.`;
}

export function StakeholderBrief({
  report,
  onOpenTechnicalFinding,
  onAsk,
  reviewerNotes = new Map(),
  titled = false,
}: StakeholderBriefProps) {
  const model = buildBrief(report);
  const root = useRef<HTMLDivElement>(null);
  // Printing shows every row expanded, then puts the rows back.
  useEffect(() => {
    let closed: HTMLDetailsElement[] = [];
    const open = () => {
      closed = [...(root.current?.querySelectorAll("details:not([open])") ?? [])].filter(
        (el): el is HTMLDetailsElement => el instanceof HTMLDetailsElement,
      );
      closed.forEach((el) => (el.open = true));
    };
    const restore = () => {
      closed.forEach((el) => (el.open = false));
      closed = [];
    };
    window.addEventListener("beforeprint", open);
    window.addEventListener("afterprint", restore);
    return () => {
      window.removeEventListener("beforeprint", open);
      window.removeEventListener("afterprint", restore);
    };
  }, []);
  const coverage = briefCoverage(report);
  const name = titled ? "" : workloadName(report.terraform_repo_ref);
  // The first row opens on wider screens only; on a phone the list comes
  // first (design review, 2026-11-14).
  const [wide, setWide] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(min-width: 681px)");
    setWide(query.matches);
  }, []);
  const firstOpen = wide ? model.rows[0]?.finding.record.finding_id : undefined;
  const rowProps = (row: BriefRow, open: boolean) => ({
    row,
    open,
    reviewerNote: reviewerNotes.get(row.finding.record.finding_id) ?? null,
    onOpenTechnicalFinding,
    onAsk,
  });
  return (
    <div className="guided-report stakeholder-brief" ref={root}>
      <span className="guided-eyebrow">Stakeholder · same evidence, plain language</span>
      <h2>Stakeholder Brief</h2>
      {name && <p className="brief-workload">{name}</p>}
      <p className="guided-intro">{introText(report, model)}</p>

      <aside className="scope-note" aria-label="Review coverage">
        <strong>Review coverage</strong>
        <p>{coverage.headline}</p>
        <details>
          <summary>Coverage details</summary>
          <ul>
            {coverage.details.map((detail) => (
              <li key={detail}>{detail}</li>
            ))}
          </ul>
        </details>
      </aside>

      <p className="brief-legend">
        <strong>Commitment labels</strong> ({Object.values(TIER_LABELS).join(", ")}): {TIER_LEGEND}{" "}
        {SAFETY_SENTENCE}
      </p>

      {model.rows.length > 0 && (
        <>
          <h3 className="guided-section-heading">Findings that need a decision</h3>
          <div className="guided-findings brief-findings">
            {model.rows.map((row) => (
              <BriefFinding
                key={row.finding.record.finding_id}
                {...rowProps(row, row.finding.record.finding_id === firstOpen)}
              />
            ))}
          </div>
        </>
      )}

      {model.noAction.length > 0 && (
        <>
          <h3 className="guided-section-heading">No action proposed</h3>
          <p className="guided-section-note">
            These findings have an explicit no-action assessment. That is not a safety guarantee;
            check their evidence and any reviewer corrections.
          </p>
          <div className="guided-findings brief-findings">
            {model.noAction.map((row) => (
              <BriefFinding key={row.finding.record.finding_id} {...rowProps(row, false)} />
            ))}
          </div>
        </>
      )}

      <details className="brief-jobs">
        <summary>Different protections do different jobs</summary>
        <p>
          No single control covers everything, and not every system needs every control. This review
          only checks some of them.
        </p>
        <dl>
          {protectionJobs(model).map((job) => (
            <div key={job.name}>
              <dt>{job.name}</dt>
              <dd>
                {job.job} <em>{job.status}</em>
              </dd>
            </div>
          ))}
        </dl>
      </details>
    </div>
  );
}
