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
  // What a rule finding is about (e.g. "rds_multi_az"). Older reviews
  // don't have it.
  concern?: string | null;
  // The model's plain-language explanation; the stakeholder card built
  // from it is ReportFinding.stakeholder.
  plain?: unknown;
  created_at: string;
}

export interface FindingPresentation {
  priority: FindingPriority;
  short_label: string;
}

export type Severity = "critical" | "high" | "medium" | "low";
export interface FindingAssessment {
  version: 1;
  severity: Severity | null;
  action: "needed" | "none" | "unknown";
  source: "rule" | "model" | "reviewer" | "unassessed";
}
// A block from an older stakeholder view: a live report saved by an older
// backend (ReportFinding.stakeholder) or a demo sidecar. Only the fields
// the Stakeholder Brief reads are typed. Older blocks also carry an
// analogy, price lines, effort hours and cost-of-inaction text; those are
// never shown (ADR-0062).
export interface StakeholderCard {
  // "rule": the old catalog's text; "model": written by the model;
  // "reviewer": written by hand for a demo.
  source: "rule" | "model" | "reviewer";
  concern: string | null;
  subject: string | null;
  severity: Severity;
  title: string;
  what_could_happen: string;
  action: string;
  needs_action: boolean;
}

// Presentation facts the backend adds to a rule finding
// (backend/shared/stakeholder/presentation.py). No text and no money:
// the Stakeholder Brief's wording lives in lib/stakeholder-brief.ts.
export interface BriefMeta {
  version: 2;
  concern: string | null;
  // "recorded": the finding's stored concern; "title": inferred from the
  // rule title for reviews saved before concerns were stored.
  concern_source: "recorded" | "title" | null;
  subject: string | null;
}

export interface ReportFinding {
  independent_check?: "supported" | "not-independently-checked" | "fix-needs-confirmation";
  record: Finding;
  presentation: FindingPresentation;
  // Independent of evidence type and evidence confidence. Absent in old reports.
  assessment?: FindingAssessment;
  // Rule-finding presentation facts from a current backend.
  brief?: BriefMeta;
  // A block from an older backend or a demo sidecar (legacy reader).
  stakeholder?: StakeholderCard;
}

export interface BaselineAnswer {
  field: string;
  label: string;
  outcome: "answered" | "assumption" | "not-observable" | "stopped";
  value: string;
  policy_version: string;
}

export interface UnverifiedFinding {
  finding_id: string;
  finding: string;
  evidence: string;
  resource: string;
  category: string | null;
  concern: string | null;
  reason_code: string;
  reason: string;
  recommendation_withheld: true;
  disposition?: "disproved" | "unable-to-verify";
  checks?: Array<{ name: string; status: "passed" | "failed" | "not-run" }>;
  supporting_evidence?: Array<{ id: string; kind: string; text: string; truncated: boolean }>;
  contradicting_evidence?: Array<{ id: string; kind: string; text: string; truncated: boolean }>;
  submitted_quote?: string;
}

export interface ReviewReport {
  unverified_findings?: UnverifiedFinding[];
  disproved_findings?: UnverifiedFinding[];
  review_scope?: {
    version: "review-scope-public@1";
    known_y: number | null;
    x: number | null;
    count_complete: boolean;
    model_outcome: "completed" | "not_invoked" | "unknown";
    categories: { reviewed: number; zero_copy: number; unsupported: number; other: number } | null;
    module_gaps: Array<{ address: string; labels: string[] }>;
    gaps_complete: boolean;
    warnings: string[];
    other_reasons?: Array<{ label: string; count: number }>;
  };
  review_id: string;
  owner_id: string;
  status: "complete";
  terraform_repo_ref: string;
  created_at: string;
  cost_estimate_tier: "low" | "medium" | "high";
  baseline_answers: BaselineAnswer[];
  findings: ReportFinding[];
  analysis_quality?: AnalysisQuality;
  analysis_scope?: {
    version: "terraform-observations@2026-10-23";
    facts_emitted: number;
    omitted_resources: number;
    omitted_items: number;
    incomplete_resources: number;
    truncated: boolean;
    runtime_verified: false;
  };
  report_projection?: {
    version: 1;
    children_available: boolean;
    child_count: number;
    excluded_child_count: number;
  };
  deeper_reviews?: Array<{ parent_finding_id: string; analysis_quality: AnalysisQuality }>;
  deeper_jobs?: DeeperJob[];
  // Price totals from older backends. Kept in the stored report, never
  // read or shown (ADR-0062).
  budget?: unknown;
  // The diagram built from the code (lib/architecture.ts). Older reviews
  // have none. Checked with isArchitectureGraph before use.
  architecture?: unknown;
}

export interface DeeperJob {
  job_id: string;
  parent_finding_id: string;
  status: "pending" | "running" | "complete" | "failed";
  deadline: number;
  failure_code: string | null;
}

export interface AnalysisStageCounts {
  attempted: number;
  accepted: number;
  rejected: number;
}

export interface AnalysisQuality {
  version: 1;
  outcome: "complete" | "partial" | "rules-only" | "all-rejected" | "no-findings" | "unknown";
  model_verification: AnalysisStageCounts | null;
  schema_validation: AnalysisStageCounts | null;
  reason_codes: string[];
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
  // The report's diagram, saved before the model runs (unvalidated here;
  // see isArchitectureGraph).
  architecture?: unknown;
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
  scopeFailure?: { known_y: number; count_complete: boolean };
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

// Reservations are a conditional, checksum-bound presigned PUT.
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
}

export interface SubmitReviewResponse {
  reviewId: string;
  status: Exclude<ReviewStatus, "failed">;
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
      // Set when the quote states a price and is not shown (ADR-0062).
      quote_omitted?: "monetary-amount";
      source_url: string;
      heading_path: string;
    }
  | { kind: "resource"; address: string }
  | { kind: "requirement"; field: string; label: string };

export interface ChatParagraph {
  text: string;
  citations: ChatCitation[];
  // Cost figures the server removed from this paragraph (ADR-0062).
  amounts_removed?: number;
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
  unsupported?: string[];
  asked_at: string | null;
  model_id: string | null;
  prompt_version: string | null;
  // The public-text policy a current server applied. Absent from older
  // servers; the frontend applies the same policy either way.
  narrative_policy?: { version: string; amounts_removed: number; quotes_omitted: number };
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

// A demo's presentation sidecar (public/demos/stakeholder/<id>.json, built
// by scripts/build_demo_stakeholder.py), kept apart from the saved report.
// Version 2 holds only assessment and plain-summary fields. Version 1
// files (no `version`) also carry prices and a budget; the reader keeps
// their assessment fields and ignores the rest.
export interface StakeholderView {
  review_id: string;
  version: 1 | 2;
  presentation: string | null;
  blocks: Record<string, StakeholderCard>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const severityValues: readonly string[] = ["critical", "high", "medium", "low"];

export function isStakeholderCard(value: unknown): value is StakeholderCard {
  if (!isRecord(value)) return false;
  const textFields = ["title", "what_could_happen", "action"];
  if (!textFields.every((field) => typeof value[field] === "string")) return false;
  if (!["rule", "model", "reviewer"].includes(value.source as string)) return false;
  if (typeof value.severity !== "string" || !severityValues.includes(value.severity)) return false;
  return typeof value.needs_action === "boolean";
}

function cardOf(value: Record<string, unknown>): StakeholderCard {
  const text = (key: string) => (typeof value[key] === "string" ? (value[key] as string) : null);
  return {
    source: value.source as StakeholderCard["source"],
    concern: text("concern"),
    subject: text("subject"),
    severity: value.severity as Severity,
    title: value.title as string,
    what_could_happen: value.what_could_happen as string,
    action: value.action as string,
    needs_action: value.needs_action as boolean,
  };
}

// Reads a version 1 or 2 sidecar. Returns null for anything else, so the
// demo opens with the findings' own text instead.
export function readStakeholderView(value: unknown): StakeholderView | null {
  if (!isRecord(value) || typeof value.review_id !== "string" || !isRecord(value.blocks)) {
    return null;
  }
  const version = value.version === undefined ? 1 : value.version;
  if (version !== 1 && version !== 2) return null;
  const blocks: Record<string, StakeholderCard> = {};
  for (const [id, block] of Object.entries(value.blocks)) {
    if (!isStakeholderCard(block)) return null;
    blocks[id] = cardOf(block as unknown as Record<string, unknown>);
  }
  return {
    review_id: value.review_id,
    version,
    presentation: typeof value.presentation === "string" ? value.presentation : null,
    blocks,
  };
}

// Puts a sidecar's blocks onto the report they were built from. A v1
// budget is not copied.
export function withStakeholderView(report: ReviewReport, view: StakeholderView): ReviewReport {
  return {
    ...report,
    findings: report.findings.map((finding) => {
      const card = view.blocks[finding.record.finding_id];
      return card ? { ...finding, stakeholder: card } : finding;
    }),
  };
}
