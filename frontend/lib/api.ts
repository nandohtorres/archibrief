import {
  isSubmitReviewResponse,
  type ClarificationRequest,
  type CreateUploadRequest,
  type CreateUploadResponse,
  type ReviewReport,
  type ReviewStatusPointer,
  type SubmitReviewRequest,
  type SubmitReviewResponse,
} from "./contracts";

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

// No user accounts (ADR-0044) — gated endpoints check a single
// pre-shared admin credential sent as x-admin-key, not a per-user
// bearer token.
function requestHeaders(adminKey?: string): HeadersInit {
  return {
    "Content-Type": "application/json",
    ...(adminKey ? { "x-admin-key": adminKey } : {}),
  };
}

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!response.ok) {
    throw new ApiRequestError(
      text || `ArchiBrief API returned ${response.status}.`,
      response.status,
    );
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

export async function submitReview(
  request: SubmitReviewRequest,
  adminKey?: string,
): Promise<SubmitReviewResponse> {
  // POST /reviews is a direct API Gateway -> Step Functions StartExecution
  // integration (ADR-0016/0042, no BFF Lambda) — the response body is
  // Step Functions' own native StartExecution API response (executionArn,
  // startDate), never a {reviewId, status} shape, since this AWS_PROXY
  // integration subtype has no response transformation capability. The
  // {reviewId, status} result below is constructed from what was already
  // sent, not parsed back out of the response (Work-Project-Issues-Log.md,
  // 2026-10-01).
  const response = await fetch(`${requireApiBaseUrl()}/reviews`, {
    method: "POST",
    headers: requestHeaders(adminKey),
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new ApiRequestError(
      text || `ArchiBrief API rejected the review submission (${response.status}).`,
      response.status,
    );
  }
  return { reviewId: request.review_id, status: "pending" };
}

// ADR-0045 (2026-10-12): the first half of the direct-upload archive_path
// flow — admin-gated like every other non-demo route, since issuing a
// presigned POST is real AWS-facing work tied to this account's bucket.
export async function requestUpload(
  request: CreateUploadRequest,
  adminKey?: string,
): Promise<CreateUploadResponse> {
  const response = await fetch(`${requireApiBaseUrl()}/uploads`, {
    method: "POST",
    headers: requestHeaders(adminKey),
    body: JSON.stringify(request),
  });
  return (await readJson(response)) as CreateUploadResponse;
}

// The second half: POSTs the file straight to S3 using the presigned
// fields from requestUpload() — deliberately NOT routed through this
// API or through requestHeaders()/x-admin-key at all. S3's own presigned
// POST policy is the only authorization this request carries; adding an
// unrelated admin-key header here would do nothing but could confuse a
// future reader into thinking it's required.
export async function uploadArchiveToS3(upload: CreateUploadResponse, file: File): Promise<void> {
  const formData = new FormData();
  for (const [field, value] of Object.entries(upload.uploadFields)) {
    formData.append(field, value);
  }
  formData.append("file", file);

  const response = await fetch(upload.uploadUrl, { method: "POST", body: formData });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new ApiRequestError(
      text || `Archive upload to storage failed (${response.status}).`,
      response.status,
    );
  }
}

export async function fetchReview(
  reviewId: string,
  adminKey?: string,
): Promise<ReviewReport | ReviewStatusPointer> {
  const response = await fetch(`${requireApiBaseUrl()}/reviews/${encodeURIComponent(reviewId)}`, {
    headers: requestHeaders(adminKey),
  });
  return (await readJson(response)) as ReviewReport | ReviewStatusPointer;
}

export async function submitClarification(
  reviewId: string,
  request: ClarificationRequest,
  adminKey?: string,
): Promise<SubmitReviewResponse> {
  const response = await fetch(
    `${requireApiBaseUrl()}/reviews/${encodeURIComponent(reviewId)}/clarify`,
    {
      method: "POST",
      headers: requestHeaders(adminKey),
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

export async function requestDeeperFinding(
  reviewId: string,
  findingId: string,
  adminKey?: string,
): Promise<unknown> {
  const response = await fetch(
    `${requireApiBaseUrl()}/reviews/${encodeURIComponent(reviewId)}/findings/${encodeURIComponent(findingId)}/deeper`,
    { method: "POST", headers: requestHeaders(adminKey) },
  );
  return readJson(response);
}
