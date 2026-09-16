import type { ReportFinding, ReviewReport } from "@/lib/contracts";
import { confidenceLabel, formatFindingId } from "@/lib/workflow";

interface GuidedReportProps {
  report: ReviewReport;
  onOpenTechnicalFinding: (findingId: string) => void;
  onAsk: (finding: ReportFinding) => void;
}

export function GuidedReport({ report, onOpenTechnicalFinding, onAsk }: GuidedReportProps) {
  const visibleFindings = report.findings.filter(
    ({ presentation }) => presentation.priority !== "confirmed",
  );
  return (
    <div className="guided-report">
      <span className="guided-eyebrow">Stakeholder view · same evidence ledger</span>
      <h2>What this review means for payments-api</h2>
      <p className="guided-intro">
        Three high-risk configuration gaps warrant validation before production. They indicate
        focused control work—not proof that the architecture requires a redesign.
      </p>

      <aside className="scope-note">
        <strong>What ArchiBrief can and cannot establish</strong>
        <p>
          It statically reviewed the submitted Terraform and workload brief. It did not run code,
          inspect live AWS, certify compliance, or resolve unsubmitted remote modules.
        </p>
      </aside>

      <section className="stakeholder-summary" aria-labelledby="stakeholder-summary-heading">
        <h3 id="stakeholder-summary-heading">Decision summary</h3>
        <p>
          First validate public-access controls, narrow the Lambda role, and confirm whether
          organization-level CloudTrail already covers this account.
        </p>
        <p>
          <strong>Coverage limit:</strong> data-residency requirements were not supplied, so
          dependent conclusions remain not observable.
        </p>
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
        {visibleFindings.map((finding, index) => (
          <details key={finding.record.finding_id} open={index === 0}>
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
                <strong>Confidence: {confidenceLabel(finding.record.confidence)}.</strong> Based on
                the evidence inputs recorded in the technical view; it is not a safety guarantee.
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
        ))}
      </div>
    </div>
  );
}
