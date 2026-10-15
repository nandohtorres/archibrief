import type { FindingPriority, ReportFinding } from "./contracts";

export type AppScreen = "submission" | "preflight" | "progress" | "clarify" | "report" | "failure";
export type FindingFilter = "all" | FindingPriority;
export type FindingSort = "priority" | "confidence" | "title";

const priorityRank: Record<FindingPriority, number> = {
  high: 4,
  review: 3,
  unknown: 2,
  confirmed: 1,
};

export function filterAndSortFindings(
  findings: ReportFinding[],
  query: string,
  filter: FindingFilter,
  sort: FindingSort,
): ReportFinding[] {
  const normalizedQuery = query.trim().toLowerCase();
  return findings
    .filter(({ record, presentation }) => {
      const matchesFilter = filter === "all" || presentation.priority === filter;
      const haystack = `${record.finding} ${record.category} ${record.type}`.toLowerCase();
      return matchesFilter && haystack.includes(normalizedQuery);
    })
    .sort((left, right) => {
      if (sort === "confidence") return right.record.confidence - left.record.confidence;
      if (sort === "title") return left.record.finding.localeCompare(right.record.finding);
      return priorityRank[right.presentation.priority] - priorityRank[left.presentation.priority];
    });
}

export function makeIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `review-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function confidenceLabel(confidence: number): "High" | "Medium" | "Low" {
  if (confidence >= 0.85) return "High";
  if (confidence >= 0.6) return "Medium";
  return "Low";
}

export function formatFindingId(findingId: string): string {
  const suffix = findingId.split("-").at(-1) ?? findingId;
  return `F-${suffix.padStart(3, "0")}`;
}
