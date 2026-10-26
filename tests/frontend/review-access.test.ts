import {
  archiveDigest,
  reviewAccessHeaders,
  storeReviewAccess,
  saveActiveReview,
  loadActiveReview,
  clearActiveReview,
  acceptSharedAccess,
  canChangeReview,
  canOpenReview,
  recentReviews,
  shareLink,
  rememberReview,
} from "../../frontend/lib/review-access";

afterEach(() => vi.unstubAllGlobals());

test("read and write credentials stay separate and expire in this tab", () => {
  const data = new Map<string, string>();
  vi.stubGlobal("window", {
    sessionStorage: {
      getItem: (key: string) => data.get(key) ?? null,
      setItem: (key: string, value: string) => data.set(key, value),
    },
  });
  storeReviewAccess("r1", {
    readToken: "r".repeat(43),
    writeToken: "w".repeat(43),
    expiresAt: Date.now() / 1000 + 100,
  });
  expect(reviewAccessHeaders("r1")).toEqual({
    "x-review-read-token": "r".repeat(43),
  });
  expect(reviewAccessHeaders("r1", true)).toEqual({
    "x-review-write-token": "w".repeat(43),
  });
  expect(reviewAccessHeaders("other")).toEqual({});
  storeReviewAccess("r1", {
    readToken: "r".repeat(43),
    writeToken: "w".repeat(43),
    expiresAt: 1,
  });
  expect(reviewAccessHeaders("r1")).toEqual({});
});

test("archive digest matches the SHA-256 checksum contract", async () => {
  expect(await archiveDigest(new File(["hello"], "example.tar"))).toBe(
    "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
  );
});

test("reload recovery is tab-scoped, bound to its API and cannot renew the deadline", () => {
  const data = new Map<string, string>();
  vi.stubGlobal("window", {
    sessionStorage: {
      getItem: (key: string) => data.get(key) ?? null,
      setItem: (key: string, value: string) => data.set(key, value),
      removeItem: (key: string) => data.delete(key),
    },
  });
  const startedAt = Date.now() - 60_000;
  saveActiveReview("r1", "/api", startedAt);
  expect(loadActiveReview("/api")).toBeNull(); // No valid capability.
  storeReviewAccess("r1", {
    readToken: "r".repeat(43),
    writeToken: "w".repeat(43),
    expiresAt: Date.now() / 1000 + 100,
  });
  expect(loadActiveReview("/api")).toEqual({ reviewId: "r1", startedAt });
  expect(loadActiveReview("/different-api")).toBeNull();
  expect(JSON.parse(data.get("archibrief.active-review")!)).not.toHaveProperty(
    "readToken",
  );
  clearActiveReview();
  expect(loadActiveReview("/api")).toBeNull();
  expect(reviewAccessHeaders("r1")).toHaveProperty("x-review-read-token");
});

function stubStores() {
  const local = new Map<string, string>();
  const session = new Map<string, string>();
  const store = (data: Map<string, string>) => ({
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => data.set(key, value),
    removeItem: (key: string) => data.delete(key),
  });
  vi.stubGlobal("window", {
    localStorage: store(local),
    sessionStorage: store(session),
  });
  return { local, session };
}

const access = (expiresAt: number) => ({
  readToken: "r".repeat(43),
  writeToken: "w".repeat(43),
  expiresAt,
});

test("review access persists in localStorage so a later visit can reopen it", () => {
  const { local, session } = stubStores();
  storeReviewAccess("r1", access(Date.now() / 1000 + 100));
  expect(local.has("archibrief.review.r1")).toBe(true);
  expect(session.has("archibrief.review.r1")).toBe(false);
  expect(canOpenReview("r1")).toBe(true);
  expect(canOpenReview("unknown")).toBe(false);
});

test("recent reviews list newest first, at most five, and drop expired access", () => {
  stubStores();
  for (let i = 0; i < 7; i++) {
    storeReviewAccess(`r${i}`, access(Date.now() / 1000 + 100));
    rememberReview(`r${i}`, `Review ${i}`, 1000 + i);
  }
  expect(recentReviews().map((r) => r.reviewId)).toEqual([
    "r6",
    "r5",
    "r4",
    "r3",
    "r2",
  ]);
  storeReviewAccess("r6", access(1)); // Expired.
  expect(recentReviews().map((r) => r.reviewId)).toEqual([
    "r5",
    "r4",
    "r3",
    "r2",
  ]);
  rememberReview("r2", "Review 2 again", 5000);
  expect(recentReviews()[0]).toEqual({
    reviewId: "r2",
    label: "Review 2 again",
    submittedAt: 5000,
  });
  expect(JSON.stringify(recentReviews())).not.toContain("r".repeat(43)); // No tokens in the list.
});

test("share links carry only the read key, in the fragment, and never downgrade the owner", () => {
  const { local } = stubStores();
  storeReviewAccess("r1", access(Date.now() / 1000 + 100));
  const link = new URL(shareLink("r1", "https://archibrief.dev/?demo=x#old")!);
  expect(link.searchParams.get("review")).toBe("r1");
  expect(link.searchParams.has("demo")).toBe(false);
  expect(link.hash).toContain("access=" + "r".repeat(43));
  expect(link.href).not.toContain("w".repeat(43));
  // The owner opening their own link keeps write access.
  expect(acceptSharedAccess("r1", link.hash)).toBe(true);
  expect(canChangeReview("r1")).toBe(true);

  // Another browser gets read-only access.
  local.clear();
  expect(acceptSharedAccess("r1", link.hash)).toBe(true);
  expect(canOpenReview("r1")).toBe(true);
  expect(canChangeReview("r1")).toBe(false);
  expect(reviewAccessHeaders("r1", true)).toEqual({});

  local.clear();
  expect(
    acceptSharedAccess("r1", "#access=" + "r".repeat(43) + "&expires=1"),
  ).toBe(false);
  expect(acceptSharedAccess("r1", "#access=short&expires=9999999999")).toBe(
    false,
  );
  expect(canOpenReview("r1")).toBe(false);
});
