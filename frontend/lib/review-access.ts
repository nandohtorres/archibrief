// A review's capabilities stay in this browser (localStorage, falling back
// to this tab's sessionStorage) until the review expires, and never go into
// a URL. That is what lets a visitor reopen their recent reviews later.
type Capabilities = { readToken: string; writeToken: string; expiresAt: number };
const ACTIVE_REVIEW_KEY = "archibrief.active-review";
const RECENT_REVIEWS_KEY = "archibrief.recent-reviews";
const MAX_RECENT_REVIEWS = 5;
const REVIEW_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

export type RecentReview = { reviewId: string; label: string; submittedAt: number };

function browserStores(): Storage[] {
  const stores: Storage[] = [];
  for (const name of ["localStorage", "sessionStorage"] as const) {
    try {
      const store = (window as unknown as Record<string, Storage | undefined>)[name];
      if (store) stores.push(store);
    } catch {
      /* Storage access denied. */
    }
  }
  return stores;
}

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
      !REVIEW_ID.test(value.reviewId) ||
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
  for (const store of browserStores()) {
    try {
      store.setItem(`archibrief.review.${reviewId}`, JSON.stringify(value));
      return;
    } catch {
      /* Try the next store. */
    }
  }
}

function storedAccess(reviewId: string): string | null {
  for (const store of browserStores()) {
    try {
      const raw = store.getItem(`archibrief.review.${reviewId}`);
      if (raw) return raw;
    } catch {
      /* Try the next store. */
    }
  }
  return null;
}

export function reviewAccessHeaders(reviewId: string, write = false): Record<string, string> {
  if (typeof window === "undefined") return {};
  try {
    const raw = storedAccess(reviewId);
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

// Remembers a submitted review for the home page's "Your recent reviews".
export function rememberReview(reviewId: string, label: string, submittedAt = Date.now()): void {
  if (typeof window === "undefined" || !REVIEW_ID.test(reviewId)) return;
  const entry: RecentReview = { reviewId, label: label.slice(0, 120), submittedAt };
  const others = recentReviews().filter((saved) => saved.reviewId !== reviewId);
  const next = [entry, ...others].slice(0, MAX_RECENT_REVIEWS);
  for (const store of browserStores()) {
    try {
      store.setItem(RECENT_REVIEWS_KEY, JSON.stringify(next));
      return;
    } catch {
      /* Try the next store. */
    }
  }
}

// This browser's reviews that can still be opened, newest first. Expired
// ones drop out because their capability no longer authorizes a read.
export function recentReviews(): RecentReview[] {
  if (typeof window === "undefined") return [];
  for (const store of browserStores()) {
    try {
      const value: unknown = JSON.parse(store.getItem(RECENT_REVIEWS_KEY) ?? "null");
      if (!Array.isArray(value)) continue;
      return value
        .filter(
          (entry): entry is RecentReview =>
            typeof entry?.reviewId === "string" &&
            REVIEW_ID.test(entry.reviewId) &&
            typeof entry.label === "string" &&
            typeof entry.submittedAt === "number" &&
            Number.isFinite(entry.submittedAt),
        )
        .filter((entry) => Boolean(reviewAccessHeaders(entry.reviewId)["x-review-read-token"]))
        .sort((a, b) => b.submittedAt - a.submittedAt)
        .slice(0, MAX_RECENT_REVIEWS);
    } catch {
      /* Try the next store. */
    }
  }
  return [];
}

export function canOpenReview(reviewId: string): boolean {
  return REVIEW_ID.test(reviewId) && Boolean(reviewAccessHeaders(reviewId)["x-review-read-token"]);
}

export async function archiveDigest(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
