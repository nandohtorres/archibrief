import { submitReview } from "../../frontend/lib/api";

beforeEach(() =>
  vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.example.test"),
);
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

const request = { review_id: "r1" } as Parameters<typeof submitReview>[0];

test("a throttled request says to wait instead of showing the raw body", async () => {
  vi.stubGlobal(
    "fetch",
    async () =>
      new Response('{"message":"Too Many Requests"}', { status: 429 }),
  );
  await expect(submitReview(request)).rejects.toThrow(
    "Too many requests right now. Wait a minute and try again.",
  );
});

test("a known handler error keeps its own message", async () => {
  vi.stubGlobal(
    "fetch",
    async () => new Response('{"error":"paid_limit_reached"}', { status: 429 }),
  );
  await expect(submitReview(request)).rejects.toThrow(
    "The review allowance is used up. Please try again tomorrow.",
  );
});
