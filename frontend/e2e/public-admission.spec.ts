import { expect, test, type Page } from "@playwright/test";
import { PUBLIC_URL } from "../playwright.config";
import { fixtureReport } from "../lib/fixtures";
import { fillSubmission } from "./support/submission";
import { mockTurnstile } from "./support/turnstile";

const REVIEW_ID = "12345678-1234-4234-8234-123456789abc";

async function reservation(
  page: Page,
  url: string,
  options: { quota?: boolean; version?: boolean } = {},
) {
  await page.route("**/mock-api/uploads", async (route) => {
    const request = route.request().postDataJSON();
    expect(request.archive_size).toBeGreaterThan(0);
    expect(request.archive_sha256).toMatch(/^[a-f0-9]{64}$/);
    expect(request.review_id).toBeUndefined();
    await route.fulfill({
      status: options.quota ? 429 : 200,
      contentType: "application/json",
      body: JSON.stringify(
        options.quota
          ? { error: "upload_limit_reached" }
          : {
              reviewId: REVIEW_ID,
              archiveKey: `uploads/${REVIEW_ID}/archive.tar`,
              uploadUrl: `${url}/mock-api/bound-upload`,
              uploadMethod: "PUT",
              uploadHeaders: {
                "Content-Type": "application/x-tar",
                "If-None-Match": "*",
                "x-amz-checksum-sha256": "fixture-checksum",
              },
              readToken: "r".repeat(43),
              writeToken: "w".repeat(43),
              expiresAt: Math.floor(Date.now() / 1000) + 3600,
            },
      ),
    });
  });
  await page.route("**/mock-api/bound-upload", async (route) => {
    expect(route.request().method()).toBe("PUT");
    expect(route.request().headers()["if-none-match"]).toBe("*");
    expect(route.request().headers()["x-admin-key"]).toBeUndefined();
    await route.fulfill({
      status: 200,
      headers: options.version === false ? {} : { "x-amz-version-id": "fixture-version" },
      body: "",
    });
  });
  await page.route("**/mock-api/reviews", async (route) => {
    const request = route.request().postDataJSON();
    expect(request.review_id).toBe(REVIEW_ID);
    expect(request.archive_version_id).toBe("fixture-version");
    expect(route.request().headers()["x-review-write-token"]).toBe("w".repeat(43));
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ reviewId: REVIEW_ID, status: "pending" }),
    });
  });
  await page.route(`**/mock-api/reviews/${REVIEW_ID}`, async (route) => {
    expect(route.request().headers()["x-review-read-token"]).toBe("r".repeat(43));
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ ...fixtureReport, review_id: REVIEW_ID }),
    });
  });
  await page.route("**/mock-api/reviews/*/questions", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        review_id: REVIEW_ID,
        questions: [],
        suggested: [],
        questions_remaining: 5,
        limit: 5,
      }),
    }),
  );
}

async function fill(page: Page) {
  await page.goto(PUBLIC_URL);
  await fillSubmission(page);
  await expect(page.getByRole("button", { name: "Start review" })).toBeEnabled();
}

test("upload uses the server ID, exact S3 version and separate capabilities", async ({ page }) => {
  await mockTurnstile(page);
  await reservation(page, PUBLIC_URL);
  await fill(page);
  await page.getByRole("button", { name: "Start review" }).click();
  await expect(page.getByRole("button", { name: "Export ledger" })).toBeVisible();
});

test("reload resumes the same review without a new upload or dispatch", async ({ page }) => {
  await mockTurnstile(page);
  await reservation(page, PUBLIC_URL);
  let uploads = 0;
  let dispatches = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/mock-api/uploads")) uploads++;
    if (request.url().endsWith("/mock-api/reviews")) dispatches++;
  });
  await fill(page);
  await page.getByRole("button", { name: "Start review" }).click();
  await expect(page.getByRole("button", { name: "Export ledger" })).toBeVisible();
  await page.getByRole("button", { name: "New review", exact: true }).click();
  await page.getByRole("button", { name: "Resume last review in this tab" }).click();
  await expect(page.getByRole("button", { name: "Export ledger" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: "Export ledger" })).toBeVisible();
  expect(uploads).toBe(1);
  expect(dispatches).toBe(1);
  expect(page.url()).not.toContain("token");
});

test("a transient status failure retries the same accepted review", async ({ page }) => {
  await mockTurnstile(page);
  await reservation(page, PUBLIC_URL);
  let reads = 0;
  await page.route(`**/mock-api/reviews/${REVIEW_ID}`, async (route) => {
    reads++;
    await route.fulfill({
      status: reads === 1 ? 503 : 200,
      contentType: "application/json",
      body: JSON.stringify(
        reads === 1 ? { error: "busy" } : { ...fixtureReport, review_id: REVIEW_ID },
      ),
    });
  });
  await fill(page);
  await page.getByRole("button", { name: "Start review" }).click();
  await expect(page.getByRole("button", { name: "Export ledger" })).toBeVisible();
  expect(reads).toBe(2);
});

test("verification completes before bound upload admission", async ({ page }) => {
  await mockTurnstile(page);
  await reservation(page, PUBLIC_URL);
  await fill(page);
  await page.getByRole("button", { name: "Start review" }).click();
  await expect(page.getByRole("button", { name: "Export ledger" })).toBeVisible();
});

test("challenge failure keeps anonymous submission disabled", async ({ page }) => {
  await mockTurnstile(page, false);
  await page.goto(PUBLIC_URL);
  await fillSubmission(page);
  await expect(
    page.getByText("Verification is unavailable. Please try again shortly."),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Start review" })).toBeDisabled();
});

test("missing storage version prevents review dispatch", async ({ page }) => {
  await mockTurnstile(page);
  await reservation(page, PUBLIC_URL, { version: false });
  let dispatched = false;
  page.on("request", (request) => {
    if (request.url().endsWith("/mock-api/reviews")) dispatched = true;
  });
  await fill(page);
  await page.getByRole("button", { name: "Start review" }).click();
  await expect(page.getByText("Storage did not return an upload version.")).toBeVisible();
  expect(dispatched).toBe(false);
});

test("quota rejection does not upload or dispatch a review", async ({ page }) => {
  await mockTurnstile(page);
  await reservation(page, PUBLIC_URL, { quota: true });
  let uploaded = false;
  page.on("request", (request) => {
    if (request.url().includes("bound-upload")) uploaded = true;
  });
  await fill(page);
  await page.getByRole("button", { name: "Start review" }).click();
  await expect(
    page.getByText("Today's upload allowance is used up. Please try again tomorrow."),
  ).toBeVisible();
  expect(uploaded).toBe(false);
});

test("dispatch retry reuses the bound file without a second reservation", async ({ page }) => {
  await mockTurnstile(page);
  await reservation(page, PUBLIC_URL);
  let reservations = 0;
  let uploads = 0;
  let dispatches = 0;
  page.on("request", (request) => {
    if (request.url().endsWith("/mock-api/uploads")) reservations++;
    if (request.url().endsWith("/mock-api/bound-upload")) uploads++;
  });
  await page.route("**/mock-api/reviews", async (route) => {
    dispatches++;
    await route.fulfill({
      status: dispatches === 1 ? 503 : 202,
      contentType: "application/json",
      body: JSON.stringify(
        dispatches === 1
          ? { error: "dispatch_unavailable" }
          : { reviewId: REVIEW_ID, status: "pending" },
      ),
    });
  });
  await fill(page);
  await page.getByRole("button", { name: "Start review" }).click();
  await expect(page.getByRole("button", { name: "Edit submission" })).toBeVisible();
  await page.getByRole("button", { name: "Edit submission" }).click();
  await page.getByRole("button", { name: "Start review" }).click();
  await expect(page.getByRole("button", { name: "Export ledger" })).toBeVisible();
  expect(reservations).toBe(1);
  expect(uploads).toBe(1);
  expect(dispatches).toBe(2);
});
