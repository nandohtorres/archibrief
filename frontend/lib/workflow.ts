import type { FindingType, ReportFinding } from "./contracts";
import { assessmentFor, compareAssessments } from "./assessment";

export type AppScreen = "submission" | "preflight" | "progress" | "report" | "failure";
// Where the report on screen came from: the public sample (GET /demo),
// a real review the admin ran, or the bundled fixture in a build with no
// API configured. Drives labels and whether paid actions are offered.
// "demo": a saved review of real public Terraform (lib/demos.ts).
export type ReportSource = "sample" | "demo" | "live" | "fixture";
export type FindingFilter =
  "all" | "needed" | "none" | "unknown" | "critical" | "high" | "medium" | "low";
export type FindingSort = "priority" | "confidence" | "title";

export function filterAndSortFindings(
  findings: ReportFinding[],
  query: string,
  filter: FindingFilter,
  sort: FindingSort,
): ReportFinding[] {
  const normalizedQuery = query.trim().toLowerCase();
  return findings
    .filter((finding) => {
      const { record } = finding;
      const assessment = assessmentFor(finding);
      const matchesFilter =
        filter === "all" || assessment.action === filter || assessment.severity === filter;
      const haystack = `${record.finding} ${record.category} ${record.type}`.toLowerCase();
      return matchesFilter && haystack.includes(normalizedQuery);
    })
    .sort((left, right) => {
      if (sort === "confidence") return right.record.confidence - left.record.confidence;
      if (sort === "title") return left.record.finding.localeCompare(right.record.finding);
      return compareAssessments(left, right);
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
  malformed_configuration:
    "This configuration declares the same resource or module twice. Make each name unique within its module and start a new review. No AI analysis was started.",
  input_blocked:
    "Your workload brief was flagged by our safety checks. Rephrase it as a plain description of the system and try again.",
  paused: "Reviews are temporarily paused. Please try again later.",
  timed_out: "The review took too long to finish. Please try again in a few minutes.",
  clarification_expired:
    "This review expired while waiting for your answers. Please start a new review.",
  clarification_retired:
    "This review was waiting on a question ArchiBrief no longer asks after submission. Please start a new review.",
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
  return workloadName(terraformRepoRef) || "Architecture review";
}

// The report name is optional on the form: left blank, the report is
// named after the uploaded file ("payments.tar.gz" -> "payments"), or as
// pasted Terraform.
export function defaultReportName(source: "upload" | "paste", archiveFile: File | null): string {
  if (source === "paste") return "Pasted Terraform";
  const fileName = archiveFile?.name.replace(/\.(tar\.gz|tgz|tar)$/i, "").trim();
  return fileName || "Untitled review";
}

export const reportSourceLabels: Record<ReportSource, string> = {
  sample: "Sample review · hypothetical workload",
  demo: "Demo review · real public Terraform, checked by hand",
  live: "Complete · evidence ledger",
  fixture: "Complete · fixture evidence ledger",
};
