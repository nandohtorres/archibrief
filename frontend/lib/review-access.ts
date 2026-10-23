// Capabilities stay in this tab, out of URLs and persistent localStorage.
type Capabilities = { readToken: string; writeToken: string; expiresAt: number };

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
