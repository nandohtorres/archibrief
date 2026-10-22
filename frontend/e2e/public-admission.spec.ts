import { expect, test, type Page } from "@playwright/test";
import { LIVE_URL, PUBLIC_URL } from "../playwright.config";
import { fixtureReport } from "../lib/fixtures";
import { fillSubmission } from "./support/submission";

const REVIEW_ID = "12345678-1234-4234-8234-123456789abc";

async function challenge(page: Page, succeed = true) {
  await page.route("https://challenges.cloudflare.com/**", async (route) => {
    const onload = new URL(route.request().url()).searchParams.get("onload");
    await route.fulfill({
      contentType: "application/javascript",
      body: `
      window.turnstile = {
        render: (element, options) => { setTimeout(() => options[${JSON.stringify(succeed ? "callback" : "error-callback")}]?.(${JSON.stringify(succeed ? "mock-challenge" : "network-error")}), 10); return 'test-widget'; },
        reset: () => {}, remove: () => {}, getResponse: () => 'mock-challenge', isExpired: () => false
      };
      ${onload ? `window[${JSON.stringify(onload)}]?.();` : ""}
    `,
    });
  });
}

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
        limit_applies: true,
      }),
    }),
  );
}

async function fill(page: Page, url: string, admin = false) {
  await page.goto(url);
  if (admin) await page.getByLabel("Admin key").fill("test-admin-key");
  await fillSubmission(page);
}

test("admin upload uses the server ID, exact S3 version and separate capabilities", async ({
  page,
}) => {
  await reservation(page, LIVE_URL);
  await fill(page, LIVE_URL, true);
  await page.getByRole("button", { name: "Start review" }).click();
  await expect(page.getByRole("button", { name: "Export ledger" })).toBeVisible();
});

test("anonymous preview completes verification before bound upload admission", async ({ page }) => {
  await challenge(page);
  await reservation(page, PUBLIC_URL);
  await fill(page, PUBLIC_URL);
  await expect(page.getByRole("button", { name: "Start review" })).toBeEnabled();
  await page.getByRole("button", { name: "Start review" }).click();
  await expect(page.getByRole("button", { name: "Export ledger" })).toBeVisible();
});

test("challenge failure keeps anonymous submission disabled", async ({ page }) => {
  await challenge(page, false);
  await fill(page, PUBLIC_URL);
  await expect(
    page.getByText("Verification is unavailable. Please try again shortly."),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Start review" })).toBeDisabled();
});

test("missing storage version prevents review dispatch", async ({ page }) => {
  await reservation(page, LIVE_URL, { version: false });
  let dispatched = false;
  page.on("request", (request) => {
    if (request.url().endsWith("/mock-api/reviews")) dispatched = true;
  });
  await fill(page, LIVE_URL, true);
  await page.getByRole("button", { name: "Start review" }).click();
  await expect(page.getByText("Storage did not return an upload version.")).toBeVisible();
  expect(dispatched).toBe(false);
});

test("quota rejection does not upload or dispatch a review", async ({ page }) => {
  await reservation(page, LIVE_URL, { quota: true });
  let uploaded = false;
  page.on("request", (request) => {
    if (request.url().includes("bound-upload")) uploaded = true;
  });
  await fill(page, LIVE_URL, true);
  await page.getByRole("button", { name: "Start review" }).click();
  await expect(
    page.getByText("Today's upload allowance is used up. Please try again tomorrow."),
  ).toBeVisible();
  expect(uploaded).toBe(false);
});

test("dispatch retry reuses the bound file without a second reservation", async ({ page }) => {
  await reservation(page, LIVE_URL);
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
  await fill(page, LIVE_URL, true);
  await page.getByRole("button", { name: "Start review" }).click();
  await expect(page.getByRole("button", { name: "Edit submission" })).toBeVisible();
  await page.getByRole("button", { name: "Edit submission" }).click();
  await page.getByRole("button", { name: "Start review" }).click();
  await expect(page.getByRole("button", { name: "Export ledger" })).toBeVisible();
  expect(reservations).toBe(1);
  expect(uploads).toBe(1);
  expect(dispatches).toBe(2);
});
