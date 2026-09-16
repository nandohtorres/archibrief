import {
  isSubmitReviewResponse,
  type ClarificationRequest,
  type ReviewReport,
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
  const response = await fetch(`${requireApiBaseUrl()}/reviews`, {
    method: "POST",
    headers: requestHeaders(adminKey),
    body: JSON.stringify(request),
  });
  const value = await readJson(response);
  if (!isSubmitReviewResponse(value)) {
    throw new ApiRequestError(
      "ArchiBrief API returned an unexpected submission response.",
      response.status,
    );
  }
  return value;
}

export async function fetchReview(reviewId: string, adminKey?: string): Promise<ReviewReport> {
  const response = await fetch(`${requireApiBaseUrl()}/reviews/${encodeURIComponent(reviewId)}`, {
    headers: requestHeaders(adminKey),
  });
  return (await readJson(response)) as ReviewReport;
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
