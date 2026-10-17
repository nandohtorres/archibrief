import type { FindingPriority, ReportFinding, ReviewReport } from "./contracts";

export type AppScreen = "submission" | "preflight" | "progress" | "clarify" | "report" | "failure";
// Where the report on screen came from: the public sample (GET /demo),
// a real review the admin ran, or the bundled fixture in a build with no
// API configured. Drives labels and whether paid actions are offered.
// "demo": a saved review of real public Terraform (lib/demos.ts).
export type ReportSource = "sample" | "demo" | "live" | "fixture";
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

// "github.com/example/payments-api@a91f3c2" -> "payments-api"; "" when the
// reference has no recognizable name.
export function workloadName(terraformRepoRef: string): string {
  return terraformRepoRef.split("@")[0].split("/").filter(Boolean).pop()?.trim() ?? "";
}

export function reportTitle(terraformRepoRef: string): string {
  const name = workloadName(terraformRepoRef);
  return name ? `${name} architecture review` : "Architecture review";
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

export interface StakeholderSummary {
  heading: string;
  intro: string;
  startWith: string[];
  coverageLimits: string[];
}

// The stakeholder view's headline text, built from the real report. It
// used to be fixed sample wording ("payments-api", "Three high-risk
// gaps"), so a live review of any other system showed the sample's
// conclusions (master-list 15c). Wording stays factual: counts, the
// findings' own titles, and which workload answers were not supplied.
// `titled`: the page already shows a real title (a demo's), so the
// heading doesn't repeat a name derived from the repository label.
export function stakeholderSummary(report: ReviewReport, titled = false): StakeholderSummary {
  const name = titled ? "" : workloadName(report.terraform_repo_ref);
  const high = report.findings.filter(({ presentation }) => presentation.priority === "high");
  const review = report.findings.filter(({ presentation }) => presentation.priority === "review");

  const toReview = plural(review.length, "item", "items");
  const intro =
    high.length > 0
      ? `${plural(high.length, "high-risk configuration gap was", "high-risk configuration gaps were")} found by deterministic checks` +
        (review.length > 0 ? `, plus ${toReview} to review` : "") +
        ". Each points to specific settings to change; none of them alone means the architecture needs a redesign."
      : "No high-risk configuration gaps were found by the deterministic checks." +
        (review.length > 0
          ? ` ${toReview} to review ${review.length === 1 ? "is" : "are"} listed below.`
          : "");

  const coverageLimits = report.baseline_answers
    .filter(({ outcome }) => outcome !== "answered")
    .map(({ label, outcome }) =>
      outcome === "assumption"
        ? `${label} was not supplied, so a conservative assumption was used.`
        : `${label} was not supplied, so conclusions that depend on it are not observable.`,
    );

  return {
    heading: name ? `What this review means for ${name}` : "What this review means",
    intro,
    startWith: high.slice(0, 3).map(({ record }) => record.finding),
    coverageLimits,
  };
}

export const reportSourceLabels: Record<ReportSource, string> = {
  sample: "Sample review · hypothetical workload",
  demo: "Demo review · real public Terraform, checked by hand",
  live: "Complete · evidence ledger",
  fixture: "Complete · fixture evidence ledger",
};
