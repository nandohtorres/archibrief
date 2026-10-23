import type { ReportFinding, ReviewReport, StakeholderCard } from "@/lib/contracts";
import type { ReviewerNote } from "@/lib/demos";
import {
  confidenceLabel,
  formatDollars,
  formatFindingId,
  formatMonthly,
  orderByBudget,
  stakeholderSummary,
} from "@/lib/workflow";
import { BudgetSummary, verdictClass } from "./budget-summary";

interface GuidedReportProps {
  report: ReviewReport;
  onOpenTechnicalFinding: (findingId: string) => void;
  onAsk: (finding: ReportFinding) => void;
  // Hand-check notes when this is a demo review, keyed by finding id.
  reviewerNotes?: Map<string, ReviewerNote>;
  // True when the page shows a real title (a demo's) above this view.
  titled?: boolean;
}

interface FindingCardProps {
  finding: ReportFinding;
  reviewerNote: ReviewerNote | null;
  open: boolean;
  onOpenTechnicalFinding: (findingId: string) => void;
  onAsk: (finding: ReportFinding) => void;
}

const CARD_SOURCE_NOTES: Record<StakeholderCard["source"], string> = {
  rule: "Standard explanation for this check.",
  model: "Plain-language text written by the AI from this finding.",
  reviewer: "Plain-language text written by hand for this demo.",
};

function cardElementId(findingId: string): string {
  return `stakeholder-card-${findingId}`;
}

function CostBoxes({ card }: { card: StakeholderCard }) {
  const { fix, inaction } = card;
  if (!fix || !inaction) return null;
  return (
    <div className="cost-boxes">
      <div className="cost-box fix">
        <span>Cost to fix</span>
        <strong>{formatMonthly(fix.monthly_known, fix.has_unpriced)} / month</strong>
        <ul>
          {fix.lines.map((line) => (
            <li key={`${line.label}-${line.basis}`}>
              {line.label}:{" "}
              {line.monthly_high === null
                ? line.basis
                : `${formatDollars(line.monthly_high)}/month (${line.basis})`}
            </li>
          ))}
          <li>Engineering time: {fix.effort_label}</li>
        </ul>
        {fix.caveat && <p>{fix.caveat}</p>}
      </div>
      <div className="cost-box risk">
        <span>Cost of not fixing</span>
        <strong>{inaction.headline}</strong>
        <p>{inaction.detail}</p>
        {inaction.source_name && <p>Industry benchmark, not a predicted loss for this system.</p>}
        {inaction.method && (
          <p>
            <em>How to estimate it:</em> {inaction.method}
          </p>
        )}
        {inaction.source_name && inaction.source_url && (
          <p className="cost-source">
            Source:{" "}
            <a href={inaction.source_url} target="_blank" rel="noreferrer">
              {inaction.source_name}
            </a>
          </p>
        )}
      </div>
    </div>
  );
}

function FindingCard({
  finding,
  reviewerNote,
  open,
  onOpenTechnicalFinding,
  onAsk,
}: FindingCardProps) {
  const card = finding.stakeholder;
  return (
    <details open={open} id={cardElementId(finding.record.finding_id)}>
      <summary>
        <span className={`priority-pill ${finding.presentation.priority}`}>
          {finding.presentation.short_label}
        </span>
        <span>
          <small>
            {formatFindingId(finding.record.finding_id)} · {finding.record.category}
            {card?.subject && ` · ${card.subject}`}
          </small>
          <strong>{card ? card.title : finding.record.finding}</strong>
        </span>
        {card?.verdict && card.verdict_label && (
          <span className={`verdict-tag ${verdictClass[card.verdict]}`}>{card.verdict_label}</span>
        )}
        {card && !card.needs_action && <span className="verdict-tag none">No action needed</span>}
        <i aria-hidden="true">›</i>
      </summary>
      <div className="guided-finding-body">
        {reviewerNote && (
          <aside className="reviewer-note" aria-label="Reviewer note">
            <strong>Reviewer note · {reviewerNote.verdict}</strong>
            <p>{reviewerNote.note}</p>
          </aside>
        )}
        {card ? (
          <>
            <div className="plain-terms">
              <h4>In plain terms</h4>
              <p>{card.analogy}</p>
            </div>
            <h4>What could happen</h4>
            <p>{card.what_could_happen}</p>
            <h4>What fixing it involves</h4>
            <p>{card.action}</p>
            <CostBoxes card={card} />
            <p className="card-technical">
              <strong>Technical finding:</strong> {finding.record.finding.replace(/\.$/, "")}.{" "}
              {CARD_SOURCE_NOTES[card.source]}
            </p>
          </>
        ) : (
          <>
            <h4>Why it matters</h4>
            <p>{finding.record.risk_impact}</p>
            <h4>Recommended action</h4>
            <p>{finding.record.recommendation}</p>
          </>
        )}
        <p className="plain-confidence">
          <strong>Confidence: {confidenceLabel(finding.record.confidence)}.</strong> A rough guide
          to how direct the evidence is, from the inputs in the technical view. It doesn&apos;t
          measure whether the finding is right, and it is not a safety guarantee.
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

// From a budget row: open that finding's card and bring it into view.
function openCard(findingId: string) {
  const element = document.getElementById(cardElementId(findingId));
  if (element instanceof HTMLDetailsElement) {
    element.open = true;
    element.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

export function GuidedReport({
  report,
  onOpenTechnicalFinding,
  onAsk,
  reviewerNotes = new Map(),
  titled = false,
}: GuidedReportProps) {
  const decisionFindings = orderByBudget(
    report.findings.filter(({ presentation }) => presentation.priority !== "confirmed"),
    report.budget,
  );
  // Facts read straight from the code. Some are only context ("Multi-AZ
  // is on"), but some are real problems ("storage encryption explicitly
  // disabled"), so they're shown, in their own labeled section, rather
  // than hidden.
  const confirmedFindings = orderByBudget(
    report.findings.filter(({ presentation }) => presentation.priority === "confirmed"),
    report.budget,
  );
  const summary = stakeholderSummary(report, titled);
  return (
    <div className="guided-report">
      <span className="guided-eyebrow">Stakeholder view · same evidence ledger</span>
      <h2>{summary.heading}</h2>
      <p className="guided-intro">{summary.intro}</p>

      {report.budget && (
        <BudgetSummary budget={report.budget} placement="top" onOpenFinding={openCard} />
      )}

      <aside className="scope-note">
        <strong>What ArchiBrief can and cannot establish</strong>
        <p>
          It statically reviewed the submitted Terraform and workload brief. It did not run code,
          inspect live AWS, certify compliance, or resolve unsubmitted remote modules.
        </p>
      </aside>

      {/* The budget table already says where to start; older reviews
          without one keep the plain list. */}
      {(!report.budget || summary.coverageLimits.length > 0) && (
        <section className="stakeholder-summary" aria-labelledby="stakeholder-summary-heading">
          <h3 id="stakeholder-summary-heading">Decision summary</h3>
          {!report.budget &&
            (summary.startWith.length > 0 ? (
              <>
                <p>Start with:</p>
                <ul>
                  {summary.startWith.map((title) => (
                    <li key={title}>{title}</li>
                  ))}
                </ul>
              </>
            ) : (
              <p>No high-risk gaps need fixing first; review the items below.</p>
            ))}
          {summary.coverageLimits.map((limit) => (
            <p key={limit}>
              <strong>Coverage limit:</strong> {limit}
            </p>
          ))}
        </section>
      )}

      <div className="baseline-strip" aria-label="Workload context">
        {report.baseline_answers.map((answer, index) => (
          <div key={answer.field}>
            <span>
              0{index + 1} · {answer.outcome}
            </span>
            <strong>{answer.label}</strong>
            <p>{answer.value}</p>
          </div>
        ))}
      </div>

      <h3 className="guided-section-heading">
        {report.budget ? "What each one means" : "Findings that affect a decision"}
      </h3>
      <div className="guided-findings">
        {decisionFindings.map((finding, index) => (
          <FindingCard
            key={finding.record.finding_id}
            finding={finding}
            reviewerNote={reviewerNotes.get(finding.record.finding_id) ?? null}
            open={index === 0}
            onOpenTechnicalFinding={onOpenTechnicalFinding}
            onAsk={onAsk}
          />
        ))}
      </div>

      {confirmedFindings.length > 0 && (
        <>
          <h3 className="guided-section-heading">Reported facts</h3>
          <p className="guided-section-note">
            Findings classified as facts in the original review. This is not a safety rating; check
            their evidence and any reviewer corrections.
          </p>
          <div className="guided-findings">
            {confirmedFindings.map((finding) => (
              <FindingCard
                key={finding.record.finding_id}
                finding={finding}
                reviewerNote={reviewerNotes.get(finding.record.finding_id) ?? null}
                open={false}
                onOpenTechnicalFinding={onOpenTechnicalFinding}
                onAsk={onAsk}
              />
            ))}
          </div>
        </>
      )}

      {report.budget && (
        <BudgetSummary budget={report.budget} placement="bottom" onOpenFinding={openCard} />
      )}
    </div>
  );
}
