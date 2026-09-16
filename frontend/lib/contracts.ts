export const findingTypes = [
  "fact",
  "deterministic-rule-result",
  "inference",
  "assumption",
  "recommendation",
  "not-observable",
] as const;

export type FindingType = (typeof findingTypes)[number];

export const findingCategories = [
  "iam",
  "exposure",
  "encryption",
  "availability",
  "recovery",
  "observability",
  "cost",
] as const;

export type FindingCategory = (typeof findingCategories)[number];
export type DepthLevel = "lightweight" | "deep";
export type FindingPriority = "high" | "review" | "confirmed" | "unknown";
export type ReviewStatus = "pending" | "needs_clarification" | "complete" | "failed";

export interface Citation {
  source_url: string;
  source_edition: string;
  retrieved_at: string;
  canonical_url: string | null;
  document_id: string;
  chunk_id: string | null;
  content_hash: string;
  heading_path: string;
  exact_text_span: string;
  parser_version: string;
  corpus_version: string;
}

export interface ConfidenceInputs {
  evidence_directness: number;
  source_agreement: number;
  rule_determinism: number;
}

export interface AlternativeConsidered {
  option: string;
  reason_rejected: string;
}

export interface Finding {
  finding_id: string;
  review_id: string;
  category: FindingCategory;
  type: FindingType;
  finding: string;
  evidence: string;
  citation: Citation | null;
  confidence: number;
  confidence_inputs: ConfidenceInputs;
  risk_impact: string;
  recommendation: string;
  framework_mapping: string[];
  alternatives_considered: AlternativeConsidered[];
  depth_level: DepthLevel;
  model_id: string | null;
  prompt_version: string | null;
  corpus_version: string | null;
  retrieved_chunk_ids: string[];
  deterministic_rule_version: string | null;
  parent_finding_id: string | null;
  created_at: string;
}

export interface FindingPresentation {
  priority: FindingPriority;
  short_label: string;
}

export interface ReportFinding {
  record: Finding;
  presentation: FindingPresentation;
}

export interface BaselineAnswer {
  field: string;
  label: string;
  outcome: "answered" | "assumption" | "not-observable" | "stopped";
  value: string;
  policy_version: string;
}

export interface ReviewReport {
  review_id: string;
  owner_id: string;
  status: "complete";
  terraform_repo_ref: string;
  created_at: string;
  cost_estimate_tier: "low" | "medium" | "high";
  baseline_answers: BaselineAnswer[];
  findings: ReportFinding[];
}

export interface SubmitReviewRequest {
  terraformRepoRef: string;
  workloadBrief: string;
  idempotencyKey: string;
}

export interface SubmitReviewResponse {
  reviewId: string;
  status: Exclude<ReviewStatus, "failed">;
}

export interface ClarificationRequest {
  answers: Record<string, string>;
}

export interface PreflightField {
  id: string;
  label: string;
  question: string;
  policy: "answer" | "default" | "stopped";
  value: string;
  shownDefault?: string;
  reason: string;
}

export interface ProgressStage {
  id: string;
  label: string;
  description: string;
}

export function isSubmitReviewResponse(value: unknown): value is SubmitReviewResponse {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.reviewId === "string" &&
    (candidate.status === "pending" ||
      candidate.status === "needs_clarification" ||
      candidate.status === "complete")
  );
}
