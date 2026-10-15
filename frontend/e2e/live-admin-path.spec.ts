// Covers the "admin-gated submit review -> view findings -> 'go deeper'"
// critical path named in Work-Project-Build-Plan.md's Phase 7 E2E item.
// Built against out-live (NEXT_PUBLIC_API_BASE_URL="/mock-api" baked in
// at build time - see e2e/dev-server.mjs), with every network call
// intercepted via page.route() and answered locally. This deliberately
// never calls real AWS: a live run would trigger a real, paid Step
// Functions execution (Bedrock/AgentCore) on every CI run, which this
// suite must not do.
import { expect, test } from "@playwright/test";
import { LIVE_URL } from "../playwright.config";
import { fixtureReport } from "../lib/fixtures";

test.describe("admin-gated live critical path (mocked network)", () => {
  test("submit -> poll -> report -> go deeper", async ({ page }) => {
    // The review_id sent to the mocked API is a fresh idempotency key
    // generated client-side (makeIdempotencyKey) - capture whatever
    // actual ID the app used so the poll loop's GET can be answered
    // with a matching reviewId, rather than assuming a fixed one.
    let capturedReviewId = "";

    await page.route("**/mock-api/uploads", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          archiveKey: "archive/e2e-test.tar",
          uploadUrl: `${LIVE_URL}/mock-api/s3-upload`,
          uploadFields: {},
        }),
      });
    });
    await page.route("**/mock-api/s3-upload", async (route) => {
      await route.fulfill({ status: 204, body: "" });
    });
    await page.route("**/mock-api/reviews", async (route) => {
      const body = route.request().postDataJSON() as { review_id: string };
      capturedReviewId = body.review_id;
      await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
    });
    // Resolves "complete" on the very first poll - the pending/retry
    // loop itself is covered by the unit tests in tests/frontend for
    // archibrief-app.tsx's polling logic.
    await page.route(/\/mock-api\/reviews\/[^/]+$/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ...fixtureReport, review_id: capturedReviewId }),
      });
    });
    await page.route(/\/mock-api\/reviews\/[^/]+\/findings\/[^/]+\/deeper$/, async (route) => {
      const deeperFinding = {
        ...fixtureReport.findings[0],
        record: {
          ...fixtureReport.findings[0].record,
          finding_id: "finding-e2e-deeper-001",
          review_id: capturedReviewId,
        },
      };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ findings: [deeperFinding] }),
      });
    });

    await page.goto(LIVE_URL);
    await expect(
      page.getByRole("heading", { name: "Review an existing AWS architecture" }),
    ).toBeVisible();

    await page.getByRole("button", { name: /Detailed \(complex, cross-checked\)/ }).click();
    await expect(page.getByRole("button", { name: "Submit to deployed API" })).toBeEnabled();
    await page.getByRole("button", { name: "Submit to deployed API" }).click();

    await expect(page.locator("#report-heading")).toBeVisible({ timeout: 20_000 });
    expect(capturedReviewId).not.toBe("");

    await expect(page.getByRole("button", { name: "Go deeper" }).first()).toBeVisible();
    await page.getByRole("button", { name: "Go deeper" }).first().click();
    await expect(page.getByText(/deeper finding.*added below/)).toBeVisible();
  });
});
