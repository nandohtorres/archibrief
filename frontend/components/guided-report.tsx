import type { ReportFinding, ReviewReport } from "@/lib/contracts";
import { confidenceLabel, formatFindingId, stakeholderSummary } from "@/lib/workflow";

interface GuidedReportProps {
  report: ReviewReport;
  onOpenTechnicalFinding: (findingId: string) => void;
  onAsk: (finding: ReportFinding) => void;
}

interface FindingCardProps {
  finding: ReportFinding;
  open: boolean;
  onOpenTechnicalFinding: (findingId: string) => void;
  onAsk: (finding: ReportFinding) => void;
}

function FindingCard({ finding, open, onOpenTechnicalFinding, onAsk }: FindingCardProps) {
  return (
    <details open={open}>
      <summary>
        <span className={`priority-pill ${finding.presentation.priority}`}>
          {finding.presentation.short_label}
        </span>
        <span>
          <small>
            {formatFindingId(finding.record.finding_id)} · {finding.record.category}
          </small>
          <strong>{finding.record.finding}</strong>
        </span>
        <i aria-hidden="true">›</i>
      </summary>
      <div className="guided-finding-body">
        <h4>Why it matters</h4>
        <p>{finding.record.risk_impact}</p>
        <h4>Recommended action</h4>
        <p>{finding.record.recommendation}</p>
        <p className="plain-confidence">
          <strong>Confidence: {confidenceLabel(finding.record.confidence)}.</strong> Based on the
          evidence inputs recorded in the technical view; it is not a safety guarantee.
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

export function GuidedReport({ report, onOpenTechnicalFinding, onAsk }: GuidedReportProps) {
  const decisionFindings = report.findings.filter(
    ({ presentation }) => presentation.priority !== "confirmed",
  );
  // Facts read straight from the code. Some are only context ("Multi-AZ
  // is on"), but some are real problems ("storage encryption explicitly
  // disabled"), so they're shown, in their own labeled section, rather
  // than hidden (decision 2026-10-16).
  const confirmedFindings = report.findings.filter(
    ({ presentation }) => presentation.priority === "confirmed",
  );
  const summary = stakeholderSummary(report);
  return (
    <div className="guided-report">
      <span className="guided-eyebrow">Stakeholder view · same evidence ledger</span>
      <h2>{summary.heading}</h2>
      <p className="guided-intro">{summary.intro}</p>

      <aside className="scope-note">
        <strong>What ArchiBrief can and cannot establish</strong>
        <p>
          It statically reviewed the submitted Terraform and workload brief. It did not run code,
          inspect live AWS, certify compliance, or resolve unsubmitted remote modules.
        </p>
      </aside>

      <section className="stakeholder-summary" aria-labelledby="stakeholder-summary-heading">
        <h3 id="stakeholder-summary-heading">Decision summary</h3>
        {summary.startWith.length > 0 ? (
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
        )}
        {summary.coverageLimits.map((limit) => (
          <p key={limit}>
            <strong>Coverage limit:</strong> {limit}
          </p>
        ))}
      </section>

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

      <h3 className="guided-section-heading">Findings that affect a decision</h3>
      <div className="guided-findings">
        {decisionFindings.map((finding, index) => (
          <FindingCard
            key={finding.record.finding_id}
            finding={finding}
            open={index === 0}
            onOpenTechnicalFinding={onOpenTechnicalFinding}
            onAsk={onAsk}
          />
        ))}
      </div>

      {confirmedFindings.length > 0 && (
        <>
          <h3 className="guided-section-heading">Confirmed from the code</h3>
          <p className="guided-section-note">
            Settings read directly from the Terraform. Some are only context; check whether any of
            them matter for your workload.
          </p>
          <div className="guided-findings">
            {confirmedFindings.map((finding) => (
              <FindingCard
                key={finding.record.finding_id}
                finding={finding}
                open={false}
                onOpenTechnicalFinding={onOpenTechnicalFinding}
                onAsk={onAsk}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
