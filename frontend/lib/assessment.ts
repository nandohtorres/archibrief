import type { FindingAssessment, ReportFinding, Severity } from "./contracts";

const severities: Severity[] = ["critical", "high", "medium", "low"];
const unknown: FindingAssessment = {
  version: 1,
  severity: null,
  action: "unknown",
  source: "unassessed",
};

export function assessmentFor(finding: ReportFinding): FindingAssessment {
  if (finding.record.type === "not-observable") return unknown;
  const assessment = finding.assessment;
  if (assessment !== undefined) {
    // A malformed newer payload must not fall back to an older sidecar.
    if (
      assessment.version !== 1 ||
      !["rule", "model", "reviewer", "unassessed"].includes(assessment.source)
    )
      return unknown;
    if (
      assessment.action === "needed" &&
      assessment.severity &&
      severities.includes(assessment.severity) &&
      assessment.source !== "unassessed"
    )
      return assessment;
    if (
      assessment.action === "none" &&
      assessment.severity === null &&
      assessment.source !== "unassessed"
    )
      return assessment;
    return unknown;
  }
  // Historical demo sidecars carry explicit reviewer assessments. Never
  // derive risk from the legacy priority or from a phrase in the title.
  const card = finding.stakeholder;
  if (
    card &&
    ["rule", "model", "reviewer"].includes(card.source) &&
    severities.includes(card.severity) &&
    typeof card.needs_action === "boolean"
  ) {
    return {
      version: 1,
      severity: card.needs_action ? card.severity : null,
      action: card.needs_action ? "needed" : "none",
      source: card.source,
    };
  }
  return unknown;
}

export function compareAssessments(a: ReportFinding, b: ReportFinding): number {
  const left = assessmentFor(a);
  const right = assessmentFor(b);
  const actions = { needed: 0, unknown: 1, none: 2 };
  return (
    actions[left.action] - actions[right.action] ||
    (left.severity ? severities.indexOf(left.severity) : 4) -
      (right.severity ? severities.indexOf(right.severity) : 4)
  );
}

export function assessmentLabel(finding: ReportFinding): string {
  const assessment = assessmentFor(finding);
  if (assessment.action === "none") return "No action proposed";
  if (!assessment.severity) return "Risk unassessed";
  return `${assessment.severity[0].toUpperCase()}${assessment.severity.slice(1)} risk`;
}
