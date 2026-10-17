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
  // The diagram built from the code (lib/architecture.ts). Older reviews
  // have none. Checked with isArchitectureGraph before use.
  architecture?: unknown;
}

// GET /reviews/{reviewId}'s shape for a review that isn't complete yet
// (backend/lambdas/get_review/handler.py's `_PENDING_ALLOWED_FIELDS`) —
// a thin, raw DynamoDB-item subset, camelCase, deliberately NOT the
// snake_case ReviewReport contract, since no evidence ledger exists yet
// to assemble one from.
// preflightFields/needsClarification shapes match
// backend/agent/nodes/preflight.py's preflight_node return verbatim
// (DynamoDB stores it unmodified, get_review passes it through as-is).
// needsClarification is the LIST of paused field names
// (`event.get("needs_clarification", [])` in
// store_clarification_token.handler.py), never a boolean.
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
  // Written directly by the pipeline's RecordStage*
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

// `POST /reviews` is a direct API Gateway -> Step Functions
// StartExecution integration, no BFF Lambda (ADR-0016/0042) — this
// request body IS the raw Step Functions execution input, verbatim, so
// field names must be the snake_case ones the definition reads via bare
// "$.xxx" JSONPath references (infra/modules/step-functions-lambda/
// main.tf's "REQUIRED StartExecution Input shape" comment): review_id,
// workload_brief, retrieval_query, baseline_answers. review_id doubles
// as the idempotency token (IdempotencyGate keys off it directly) — no
// separate idempotencyKey field exists on the backend side.
//
// archive_s3_key (ADR-0045: direct upload, not server-side GitHub
// fetch). The client uploads its own
// archive straight to S3 via POST /uploads' presigned POST (see
// requestUpload()/uploadArchiveToS3() in lib/api.ts) BEFORE calling
// submitReview(), then sends the resulting key here. Required at the
// ASL layer (infra/modules/step-functions-lambda/main.tf's "REQUIRED
// StartExecution Input shape" comment) — Ingest has no other way to
// find the archive. terraform_repo_ref remains purely a display
// label (persisted by IdempotencyGate, never consumed by Ingest).
export interface SubmitReviewRequest {
  review_id: string;
  archive_version_id?: string;
  archive_s3_key: string;
  terraform_repo_ref: string;
  workload_brief: string;
  retrieval_query: string;
  baseline_answers: Record<string, string>;
}

// POST /uploads (ADR-0045) — the first half of the direct-upload flow.
// The client nonce recovers a server-issued reservation after response loss.
export interface CreateUploadRequest {
  archive_size: number;
  archive_sha256: string;
  client_request_id?: string;
  turnstile_token?: string;
}

// New reservations use conditional checksum-bound PUT; uploadFields support
// the existing admin-only POST deployment during migration.
export interface CreateUploadResponse {
  archiveKey: string;
  uploadUrl: string;
  uploadMethod?: "PUT";
  uploadedVersionId?: string;
  uploadHeaders?: Record<string, string>;
  reviewId?: string;
  readToken?: string;
  writeToken?: string;
  expiresAt?: number;
  // Temporary compatibility for the existing admin deployment and fixtures.
  uploadFields?: Record<string, string>;
}

export interface SubmitReviewResponse {
  reviewId: string;
  status: Exclude<ReviewStatus, "failed">;
}

export interface ClarificationRequest {
  answers: Record<string, string>;
  // A free-text "anything else" note shown alongside
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

// Report chat (ADR-0050): POST/GET /reviews/{reviewId}/questions.
// Citations are resolved server-side; source links come from the server's
// own records, never from model text.
export type ChatCitation =
  | { kind: "finding"; finding_id: string; title: string }
  | {
      kind: "source";
      finding_id?: string;
      chunk_id?: string;
      quote: string;
      source_url: string;
      heading_path: string;
    }
  | { kind: "resource"; address: string }
  | { kind: "requirement"; field: string; label: string };

export interface ChatParagraph {
  text: string;
  citations: ChatCitation[];
}

export type ChatStatus = "answered" | "not_determinable" | "refused";

export interface ChatTurn {
  question_id: string;
  kind: "custom" | "suggested";
  suggested_id: string | null;
  question: string;
  status: ChatStatus;
  refusal_reason: string | null;
  answer: ChatParagraph[];
  asked_at: string | null;
  model_id: string | null;
  prompt_version: string | null;
}

export interface AskQuestionRequest {
  client_request_id: string;
  question?: string;
  focus_finding_id?: string | null;
  suggested_id?: string | null;
}

export interface AskQuestionResponse extends ChatTurn {
  questions_remaining: number;
  limit: number;
  limit_applies: boolean;
}

export interface SuggestedQuestion {
  id: string;
  question: string;
  answered: boolean;
}

export interface QuestionsTranscript {
  review_id: string;
  questions: ChatTurn[];
  suggested: SuggestedQuestion[];
  questions_remaining: number;
  limit: number;
  limit_applies: boolean;
}

// Pregenerated suggested answers for a demo (scripts/pregenerate_demo_chats.py,
// served from /demos/chats/<demo-id>.json).
export interface DemoChat {
  review_id: string;
  generated_at: string;
  suggested: Array<Omit<ChatTurn, "question_id" | "kind" | "asked_at">>;
}

const chatStatuses: readonly string[] = ["answered", "not_determinable", "refused"];

export function isChatTurn(value: unknown): value is ChatTurn {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.question_id === "string" &&
    typeof candidate.question === "string" &&
    typeof candidate.status === "string" &&
    chatStatuses.includes(candidate.status) &&
    Array.isArray(candidate.answer) &&
    candidate.answer.every(
      (p) =>
        typeof p === "object" &&
        p !== null &&
        typeof (p as ChatParagraph).text === "string" &&
        Array.isArray((p as ChatParagraph).citations),
    )
  );
}

export function isQuestionsTranscript(value: unknown): value is QuestionsTranscript {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.review_id === "string" &&
    Array.isArray(candidate.questions) &&
    candidate.questions.every(isChatTurn) &&
    Array.isArray(candidate.suggested) &&
    typeof candidate.questions_remaining === "number"
  );
}
