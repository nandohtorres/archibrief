import type { ReportFinding } from "@/lib/contracts";
import { assessmentFor, assessmentLabel } from "@/lib/assessment";

export function AssessmentTag({ finding }: { finding: ReportFinding }) {
  const assessment = assessmentFor(finding);
  return (
    <span
      className={`priority-pill severity-${assessment.severity ?? "unknown"}`}
      title={`Assessment source: ${assessment.source}. This is a reported assessment, not a safety guarantee.`}
    >
      {assessmentLabel(finding)} · {assessment.source}
    </span>
  );
}
