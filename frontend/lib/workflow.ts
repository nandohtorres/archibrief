import type {
  BudgetSummary,
  FindingPriority,
  FindingType,
  ReportFinding,
  ReviewReport,
} from "./contracts";

export type AppScreen = "submission" | "preflight" | "progress" | "clarify" | "report" | "failure";
// Where the report on screen came from: the public sample (GET /demo),
// a real review the admin ran, or the bundled fixture in a build with no
// API configured. Drives labels and whether paid actions are offered.
// "demo": a saved review of real public Terraform (lib/demos.ts).
export type ReportSource = "sample" | "demo" | "live" | "fixture";
export type FindingFilter = "all" | FindingPriority;
export type FindingSort = "priority" | "confidence" | "title";

export const priorityRank: Record<FindingPriority, number> = {
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

// Why a finding has no source citation. Only a not-observable finding is an
// evidence gap; a rule finding has configuration evidence instead.
export function citationGap(type: FindingType): { heading: string; body: string } {
  if (type === "not-observable") {
    return {
      heading: "No citation by design",
      body:
        "This is a typed evidence gap. A not-observable finding cannot carry a source citation " +
        "because ArchiBrief did not have evidence from which to make the conclusion.",
    };
  }
  if (type === "deterministic-rule-result") {
    return {
      heading: "Configuration evidence, not a citation",
      body:
        "A fixed rule read the submitted configuration directly; the evidence above is what it " +
        "matched. No retrieved guidance was used, so there is no source passage. The rule sees " +
        "only the submitted code, not the rest of the account.",
    };
  }
  return {
    heading: "No source citation",
    body: "This finding carries no retrieved source passage. Check its evidence above before relying on it.",
  };
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

// The report name is optional on the form: left blank, the report is
// named after the uploaded file ("payments.tar.gz" -> "payments"), or as
// pasted Terraform.
export function defaultReportName(source: "upload" | "paste", archiveFile: File | null): string {
  if (source === "paste") return "Pasted Terraform";
  const fileName = archiveFile?.name.replace(/\.(tar\.gz|tgz|tar)$/i, "").trim();
  return fileName || "Untitled review";
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

function costIntro(budget: BudgetSummary): string {
  const items = plural(budget.item_count, "item needs", "items need");
  const effort = `${budget.effort_label} of engineering`;
  if (budget.free_count === budget.item_count) {
    return `${items} attention, and every fix is free on the AWS bill. Together they take ${effort}.`;
  }
  const monthly = formatMonthly(budget.monthly_recommended, budget.recommended_has_unpriced);
  const free =
    budget.free_count > 0
      ? `${budget.free_count} of them ${budget.free_count === 1 ? "is a free settings change" : "are free settings changes"}; `
      : "";
  return `${items} attention. ${free ? `${free}the` : "The"} recommended fixes add ${monthly} a month to the AWS bill and take ${effort}.`;
}

// The stakeholder view's headline text, built from the real report rather
// than fixed sample wording. Wording stays factual: counts, the
// findings' own titles, and which workload answers were not supplied.
// `titled`: the page already shows a real title (a demo's), so the
// heading doesn't repeat a name derived from the repository label.
export function stakeholderSummary(report: ReviewReport, titled = false): StakeholderSummary {
  const name = titled ? "" : workloadName(report.terraform_repo_ref);
  const high = report.findings.filter(({ presentation }) => presentation.priority === "high");
  const review = report.findings.filter(({ presentation }) => presentation.priority === "review");

  const toReview = plural(review.length, "item", "items");
  const findingsIntro =
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

  // With a budget, lead with the answer a decision-maker asks first: what
  // it costs.
  const budget = report.budget;
  const intro = budget && budget.item_count > 0 ? costIntro(budget) : findingsIntro;

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

// "$0", "$7.59", "$3,000": cents only where they matter.
export function formatDollars(amount: number): string {
  if (amount === 0) return "$0";
  if (amount >= 100) {
    return `$${amount.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
  }
  return `$${amount.toFixed(2)}`;
}

// A fix's monthly cost, with "+ usage" when part of it can't be priced
// from the code (log volume, table size, an unlisted instance size).
export function formatMonthly(amount: number, hasUnpriced: boolean): string {
  if (hasUnpriced) return amount === 0 ? "Usage-based" : `${formatDollars(amount)} + usage`;
  return formatDollars(amount);
}

// The budget's one-sentence answer to "what will this cost us?".
export function budgetHeadline(budget: BudgetSummary): string {
  const paid = budget.item_count - budget.free_count;
  const items = plural(budget.item_count, "item needs", "items need");
  if (budget.item_count === 0) return "Nothing here needs fixing.";
  if (paid === 0) return `${items} attention, and every fix is free on the AWS bill.`;
  const free =
    budget.free_count > 0
      ? `${budget.free_count} ${budget.free_count === 1 ? "costs" : "cost"} nothing to fix`
      : "none are free";
  return `${items} attention: ${free}, the rest change the AWS bill.`;
}

// Findings in the budget's order (most urgent, cheapest first); findings
// without a stakeholder card keep their place after them.
export function orderByBudget(findings: ReportFinding[], budget?: BudgetSummary): ReportFinding[] {
  if (!budget) return findings;
  const rank = new Map(budget.rows.map((row, index) => [row.finding_id, index]));
  return [...findings].sort(
    (left, right) =>
      (rank.get(left.record.finding_id) ?? rank.size) -
      (rank.get(right.record.finding_id) ?? rank.size),
  );
}
