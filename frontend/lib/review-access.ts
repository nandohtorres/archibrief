// Capabilities stay in this tab, out of URLs and persistent localStorage.
type Capabilities = { readToken: string; writeToken: string; expiresAt: number };
const ACTIVE_REVIEW_KEY = "archibrief.active-review";

export function saveActiveReview(reviewId: string, apiBase: string, startedAt = Date.now()): void {
  try {
    window.sessionStorage.setItem(
      ACTIVE_REVIEW_KEY,
      JSON.stringify({ reviewId, apiBase, startedAt }),
    );
  } catch {
    // The current in-memory review still works when browser storage is denied.
  }
}

export function clearActiveReview(): void {
  try {
    window.sessionStorage.removeItem(ACTIVE_REVIEW_KEY);
  } catch {
    /* Storage unavailable. */
  }
}

export function loadActiveReview(
  apiBase: string | null,
): { reviewId: string; startedAt: number } | null {
  if (!apiBase || typeof window === "undefined") return null;
  try {
    const value = JSON.parse(window.sessionStorage.getItem(ACTIVE_REVIEW_KEY) ?? "null");
    if (
      !value ||
      value.apiBase !== apiBase ||
      typeof value.reviewId !== "string" ||
      !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(value.reviewId) ||
      typeof value.startedAt !== "number" ||
      !Number.isFinite(value.startedAt) ||
      value.startedAt <= 0 ||
      value.startedAt > Date.now() ||
      !reviewAccessHeaders(value.reviewId)["x-review-read-token"]
    )
      return null;
    return { reviewId: value.reviewId, startedAt: value.startedAt };
  } catch {
    return null;
  }
}

export function storeReviewAccess(reviewId: string, value: Capabilities): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(`archibrief.review.${reviewId}`, JSON.stringify(value));
}

export function reviewAccessHeaders(reviewId: string, write = false): Record<string, string> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.sessionStorage.getItem(`archibrief.review.${reviewId}`);
    if (!raw) return {};
    const value = JSON.parse(raw) as Capabilities;
    if (
      typeof value.expiresAt !== "number" ||
      !Number.isFinite(value.expiresAt) ||
      value.expiresAt <= Date.now() / 1000
    )
      return {};
    const token = write ? value.writeToken : value.readToken;
    if (typeof token !== "string" || token.length < 32) return {};
    return { [write ? "x-review-write-token" : "x-review-read-token"]: token };
  } catch {
    return {};
  }
}

export async function archiveDigest(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
