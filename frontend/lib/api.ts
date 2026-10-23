import {
  isChatTurn,
  isQuestionsTranscript,
  isReviewReport,
  isSubmitReviewResponse,
  type AskQuestionRequest,
  type AnalysisQuality,
  type AskQuestionResponse,
  type ClarificationRequest,
  type QuestionsTranscript,
  type CreateUploadRequest,
  type CreateUploadResponse,
  type ReviewReport,
  type ReviewStatusPointer,
  type SubmitReviewRequest,
  type SubmitReviewResponse,
} from "./contracts";
import { reviewAccessHeaders, storeReviewAccess } from "./review-access";
import { qualityMessage } from "./analysis-quality";

export class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly status: number | null,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

export function getApiBaseUrl(): string | null {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  return configured ? configured.replace(/\/$/, "") : null;
}

// No user accounts: a review is reached with the read/write capabilities
// issued with its upload and kept in this tab (lib/review-access.ts).
function requestHeaders(reviewId?: string, write = false): HeadersInit {
  return {
    "Content-Type": "application/json",
    ...(reviewId ? reviewAccessHeaders(reviewId, write) : {}),
  };
}

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!response.ok) {
    const messages: Record<string, string> = {
      upload_limit_reached: "Today's upload allowance is used up. Please try again tomorrow.",
      paid_limit_reached: "The review allowance is used up. Please try again tomorrow.",
      challenge_required: "Complete verification before starting a review.",
      challenge_rejected: "Verification expired or was rejected. Complete it and try again.",
      challenge_unavailable: "Verification is unavailable. Please try again shortly.",
      public_access_closed: "Public submissions are not open yet.",
      admission_unavailable: "Reviews are temporarily unavailable. Please try again later.",
      upload_mismatch: "The uploaded file doesn't match this reservation. Start a new review.",
      upload_expired: "This upload reservation expired. Start a new review.",
      dispatch_unavailable: "The review could not start. Please retry the same submission.",
      operation_conflict: "This reservation belongs to a different submission. Start a new review.",
    };
    // 429 comes from API Gateway throttling or the WAF rate rule, not a handler.
    let message =
      response.status === 429
        ? "Too many requests right now. Wait a minute and try again."
        : text || `ArchiBrief API returned ${response.status}.`;
    try {
      const body = JSON.parse(text) as { error?: string; analysis_quality?: AnalysisQuality };
      if (body.error && messages[body.error]) message = messages[body.error];
      if (body.analysis_quality?.version === 1) message = qualityMessage(body.analysis_quality);
    } catch {
      /* Older endpoints can return plain text. */
    }
    throw new ApiRequestError(message, response.status);
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new ApiRequestError("ArchiBrief API returned invalid JSON.", response.status);
  }
}

function requireApiBaseUrl(): string {
  const baseUrl = getApiBaseUrl();
  if (!baseUrl) {
    throw new ApiRequestError(
      "No live API URL is configured. Use the fixture workflow or set NEXT_PUBLIC_API_BASE_URL.",
      null,
    );
  }
  return baseUrl;
}

export async function submitReview(request: SubmitReviewRequest): Promise<SubmitReviewResponse> {
  // POST /reviews goes through the submit_review Lambda, which admits the
  // review and starts the workflow. The {reviewId, status} result below is
  // built from what was sent; the response body isn't needed.
  const response = await fetch(`${requireApiBaseUrl()}/reviews`, {
    method: "POST",
    headers: requestHeaders(request.review_id, true),
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    await readJson(response);
  }
  return { reviewId: request.review_id, status: "pending" };
}

// ADR-0045: the first half of the direct-upload archive_path flow. The
// server checks the Turnstile token and the upload limits before issuing a
// checksum-bound presigned PUT.
export async function requestUpload(request: CreateUploadRequest): Promise<CreateUploadResponse> {
  const response = await fetch(`${requireApiBaseUrl()}/uploads`, {
    method: "POST",
    headers: requestHeaders(),
    body: JSON.stringify(request),
  });
  const upload = (await readJson(response)) as CreateUploadResponse;
  if (upload.uploadMethod === "PUT") {
    if (
      !upload.reviewId ||
      !upload.readToken ||
      !upload.writeToken ||
      !upload.expiresAt ||
      !upload.uploadHeaders
    ) {
      throw new ApiRequestError("The upload reservation is incomplete.", response.status);
    }
    storeReviewAccess(upload.reviewId, {
      readToken: upload.readToken,
      writeToken: upload.writeToken,
      expiresAt: upload.expiresAt,
    });
  } else {
    throw new ApiRequestError("A bound upload reservation is required.", response.status);
  }
  return upload;
}

// Upload directly to S3 with its signed headers, without application credentials.
// A recovered grant can return an already-uploaded version after response loss.
export async function uploadArchiveToS3(
  upload: CreateUploadResponse,
  file: File,
): Promise<string | undefined> {
  if (upload.uploadMethod === "PUT") {
    if (upload.uploadedVersionId) return upload.uploadedVersionId;
    const response = await fetch(upload.uploadUrl, {
      method: "PUT",
      headers: upload.uploadHeaders,
      body: file,
    });
    if (!response.ok)
      throw new ApiRequestError("Archive upload failed. Please try again.", response.status);
    const version = response.headers.get("x-amz-version-id");
    if (!version || version === "null")
      throw new ApiRequestError("Storage did not return an upload version.", response.status);
    return version;
  }
  throw new ApiRequestError("A bound upload reservation is required.", null);
}

export async function fetchReview(reviewId: string): Promise<ReviewReport | ReviewStatusPointer> {
  const response = await fetch(`${requireApiBaseUrl()}/reviews/${encodeURIComponent(reviewId)}`, {
    headers: requestHeaders(reviewId),
  });
  return (await readJson(response)) as ReviewReport | ReviewStatusPointer;
}

// GET /demo serves a precomputed sample report (backend/lambdas/get_demo),
// never a fresh pipeline run, so it needs no review capability.
export async function fetchDemoReport(): Promise<ReviewReport> {
  const response = await fetch(`${requireApiBaseUrl()}/demo`);
  const value = await readJson(response);
  if (!isReviewReport(value)) {
    throw new ApiRequestError(
      "The sample review came back in an unexpected format.",
      response.status,
    );
  }
  return value;
}

export async function submitClarification(
  reviewId: string,
  request: ClarificationRequest,
): Promise<SubmitReviewResponse> {
  const response = await fetch(
    `${requireApiBaseUrl()}/reviews/${encodeURIComponent(reviewId)}/clarify`,
    {
      method: "POST",
      headers: requestHeaders(reviewId, true),
      body: JSON.stringify(request),
    },
  );
  const value = await readJson(response);
  if (!isSubmitReviewResponse(value)) {
    throw new ApiRequestError(
      "ArchiBrief API returned an unexpected clarification response.",
      response.status,
    );
  }
  return value;
}

export async function requestDeeperFinding(reviewId: string, findingId: string): Promise<unknown> {
  const response = await fetch(
    `${requireApiBaseUrl()}/reviews/${encodeURIComponent(reviewId)}/findings/${encodeURIComponent(findingId)}/deeper`,
    { method: "POST", headers: requestHeaders(reviewId, true) },
  );
  return readJson(response);
}

// Report chat (ADR-0050). Errors carry the server's short code (e.g.
// "review_quota_exhausted") so the UI can show a plain, specific message.
export class ChatRequestError extends ApiRequestError {
  constructor(
    message: string,
    status: number | null,
    readonly code: string,
  ) {
    super(message, status);
    this.name = "ChatRequestError";
  }
}

async function readChatJson(response: Response): Promise<unknown> {
  const text = await response.text();
  let body: unknown = null;
  try {
    body = text ? (JSON.parse(text) as unknown) : null;
  } catch {
    body = null;
  }
  if (!response.ok) {
    const code =
      typeof body === "object" &&
      body !== null &&
      typeof (body as { error?: unknown }).error === "string"
        ? (body as { error: string }).error
        : response.status === 401 || response.status === 403
          ? "chat_not_public"
          : "answer_failed";
    throw new ChatRequestError(`Chat request failed (${response.status}).`, response.status, code);
  }
  return body;
}

export async function askQuestion(
  reviewId: string,
  request: AskQuestionRequest,
): Promise<AskQuestionResponse> {
  const response = await fetch(
    `${requireApiBaseUrl()}/reviews/${encodeURIComponent(reviewId)}/questions`,
    {
      method: "POST",
      headers: requestHeaders(reviewId, true),
      body: JSON.stringify(request),
    },
  );
  const value = await readChatJson(response);
  if (!isChatTurn(value)) {
    throw new ChatRequestError(
      "The answer came back in an unexpected format.",
      response.status,
      "answer_failed",
    );
  }
  return value as AskQuestionResponse;
}

export async function fetchQuestions(reviewId: string): Promise<QuestionsTranscript> {
  const response = await fetch(
    `${requireApiBaseUrl()}/reviews/${encodeURIComponent(reviewId)}/questions`,
    { headers: requestHeaders(reviewId) },
  );
  const value = await readChatJson(response);
  if (!isQuestionsTranscript(value)) {
    throw new ChatRequestError(
      "The conversation came back in an unexpected format.",
      response.status,
      "answer_failed",
    );
  }
  return value;
}
