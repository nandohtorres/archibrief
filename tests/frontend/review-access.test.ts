import {
  archiveDigest,
  reviewAccessHeaders,
  storeReviewAccess,
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
