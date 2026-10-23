import {
  archiveDigest,
  reviewAccessHeaders,
  storeReviewAccess,
  saveActiveReview,
  loadActiveReview,
  clearActiveReview,
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
