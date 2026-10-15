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

// GET /reviews/{reviewId}'s shape for a review that isn't complete yet
// (backend/lambdas/get_review/handler.py's `_PENDING_ALLOWED_FIELDS`) —
// a thin, raw DynamoDB-item subset, camelCase, deliberately NOT the
// snake_case ReviewReport contract, since no evidence ledger exists yet
// to assemble one from. Added 2026-10-12 building real status polling —
// previously nothing in the frontend ever called fetchReview before a
// review completed, so this response shape was unhandled.
// preflightFields/needsClarification shapes match
// backend/agent/nodes/preflight.py's preflight_node return verbatim
// (DynamoDB stores it unmodified, get_review passes it through as-is).
// Found 2026-10-12, live-tested: needsClarification was previously typed
// `boolean` here, but the backend always writes it as the LIST of
// paused field names (`event.get("needs_clarification", [])` in
// store_clarification_token.handler.py) — never a boolean anywhere in
// the real data flow. Harmless until now only because nothing in the
// frontend ever read this field before a real "needs_clarification"
// status was reachable live.
export interface PreflightFieldState {
  outcome: "answered" | "assumption" | "unknown" | "paused" | "stopped";
  value: string | null;
  is_assumption: boolean;
}

export interface ReviewStatusPointer {
  reviewId: string;
  status: string;
  findingCount?: number;
  reportS3Key?: string;
  completedAt?: string;
  createdAt?: string;
  needsClarification?: string[];
  preflightFields?: Record<string, PreflightFieldState>;
  // Added 2026-10-13 — written directly by the pipeline's RecordStage*
  // Step Functions states (see infra/modules/step-functions-lambda).
  // An internal stage codename (e.g. "ingest", "reasoning") — never
  // shown verbatim to the user; see lib/progress.ts's describeProgress()
  // for the generic macro/micro-label mapping this feeds.
  currentStage?: string;
  // Set when the pipeline fails (backend/lambdas/mark_review_failed): a
  // short public code, mapped to friendly copy by failureMessageFor().
  failureCode?: string;
  failedAt?: string;
}

// Corrected 2026-10-01 (see Work-Project-Issues-Log.md): `POST /reviews`
// is a direct API Gateway -> Step Functions StartExecution integration,
// no BFF Lambda (ADR-0016/0042) — this request body IS the raw Step
// Functions execution input, verbatim. It previously used camelCase
// field names the state machine never reads (terraformRepoRef,
// workloadBrief, idempotencyKey) instead of the snake_case fields the
// definition actually requires via bare "$.xxx" JSONPath references
// (infra/modules/step-functions-lambda/main.tf's own "REQUIRED
// StartExecution Input shape" comment): review_id, workload_brief,
// retrieval_query, baseline_answers. review_id doubles as the
// idempotency token (IdempotencyGate keys off it directly) — no
// separate idempotencyKey field exists on the backend side.
//
// archive_s3_key closes the gap this comment used to describe (resolved
// 2026-10-12, ADR-0045: direct upload, not server-side GitHub-fetch —
// see that ADR for the full reasoning). The client uploads its own
// archive straight to S3 via POST /uploads' presigned POST (see
// requestUpload()/uploadArchiveToS3() in lib/api.ts) BEFORE calling
// submitReview(), then sends the resulting key here. Required at the
// ASL layer (infra/modules/step-functions-lambda/main.tf's "REQUIRED
// StartExecution Input shape" comment) — Ingest has no other way to
// find the archive. terraform_repo_ref remains purely a display
// label (persisted by IdempotencyGate, never consumed by Ingest).
export interface SubmitReviewRequest {
  review_id: string;
  archive_s3_key: string;
  terraform_repo_ref: string;
  workload_brief: string;
  retrieval_query: string;
  baseline_answers: Record<string, string>;
}

// POST /uploads (ADR-0045) — the first half of the direct-upload flow.
// review_id is the same client-generated UUID the client will later send
// as SubmitReviewRequest.review_id, so the archive can be tied to a
// review before the review itself exists anywhere server-side.
export interface CreateUploadRequest {
  review_id: string;
}

// uploadFields are passed verbatim as additional multipart form fields
// in the direct-to-S3 POST (see uploadArchiveToS3() in lib/api.ts) — the
// standard S3 presigned-POST browser upload shape, never typed further
// here since S3 owns their exact contents.
export interface CreateUploadResponse {
  archiveKey: string;
  uploadUrl: string;
  uploadFields: Record<string, string>;
}

export interface SubmitReviewResponse {
  reviewId: string;
  status: Exclude<ReviewStatus, "failed">;
}

export interface ClarificationRequest {
  answers: Record<string, string>;
  // Added 2026-10-13 — a free-text "anything else" note shown alongside
  // the structured per-field answers (clarify-step.tsx). The backend
  // (clarify_review.handler) appends this onto workload_brief for the
  // re-invoke rather than merging it into `answers`, since that's the
  // only field the model's reasoning prompt actually reads.
  additional_notes?: string;
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

// Shape check for a finished report from GET /demo (or a complete GET
// /reviews/{id}). Shallow on purpose: it guards against an error body or
// a pending pointer being rendered as a report, not against every field.
export function isReviewReport(value: unknown): value is ReviewReport {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return (
    candidate.status === "complete" &&
    typeof candidate.review_id === "string" &&
    typeof candidate.terraform_repo_ref === "string" &&
    Array.isArray(candidate.findings) &&
    Array.isArray(candidate.baseline_answers)
  );
}
