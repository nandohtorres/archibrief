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

// Longest a live review can legitimately run end to end (AgentCore alone
// may take 300s), plus headroom. Polling past this is treated as stuck.
export const REVIEW_DEADLINE_MS = 8 * 60 * 1000;

const FAILURE_MESSAGES: Record<string, string> = {
  invalid_archive:
    "We couldn't read that archive. Upload a .tar or .tar.gz containing your .tf files and try again.",
  input_blocked:
    "Your workload brief was flagged by our safety checks. Rephrase it as a plain description of the system and try again.",
  paused: "Reviews are temporarily paused. Please try again later.",
  timed_out: "The review took too long to finish. Please try again in a few minutes.",
  clarification_expired:
    "This review expired while waiting for your answers. Please start a new review.",
  clarification_limit:
    "We still couldn't settle the review's requirements after several rounds of questions. Please start a new review with a more detailed workload brief.",
  cancelled: "This review was cancelled. Please start a new review.",
};

// Maps the backend's public failure code (mark_review_failed) to copy for
// the user. Unknown or missing codes get a generic message - never raw
// error text.
export function failureMessageFor(code: string | undefined): string {
  return (
    (code && FAILURE_MESSAGES[code]) ??
    "Something went wrong on our side while running this review. Please try again."
  );
}
