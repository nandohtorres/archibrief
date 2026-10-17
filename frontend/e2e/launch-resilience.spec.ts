import { expect, test } from "@playwright/test";
import { LIVE_URL } from "../playwright.config";
import { fixtureReport } from "../lib/fixtures";

// "View sample review" now opens the featured demo from static files; these
// tests cover the GET /demo sample it falls back to, so the demo index is
// made unavailable first.
test.beforeEach(async ({ page }) => {
  await page.route("**/demos/demos.json", (route) => route.fulfill({ status: 404, body: "" }));
});

test("slow sample request stays pending, sends once, then renders", async ({ page }) => {
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  let calls = 0;
  await page.route("**/mock-api/demo", async (route) => {
    calls++;
    await held;
    await route.fulfill({ json: fixtureReport });
  });
  await page.goto(LIVE_URL);
  await page.getByRole("button", { name: "View sample review" }).first().click();
  try {
    await expect.poll(() => calls).toBe(1);
    await expect(page.locator("#report-heading")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Loading/i }).first()).toBeDisabled();
    // Hold the response long enough to exercise visible pending UI.
    await page.waitForTimeout(1500);
    expect(calls).toBe(1);
  } finally {
    release();
  }
  await expect(page.locator("#report-heading")).toBeVisible();
});

for (const failure of ["offline", "malformed", "rate-limited", "unavailable"] as const) {
  test(`sample ${failure} response is recoverable without leaking server text`, async ({
    page,
  }) => {
    let recovered = false;
    await page.route("**/mock-api/demo", async (route) => {
      if (recovered) return route.fulfill({ json: fixtureReport });
      if (failure === "offline") return route.abort("internetdisconnected");
      return route.fulfill({
        status: failure === "rate-limited" ? 429 : failure === "unavailable" ? 503 : 200,
        contentType: "application/json",
        body:
          failure === "malformed"
            ? "not-json-launch-marker"
            : '{"message":"private-server-launch-marker"}',
      });
    });
    await page.goto(LIVE_URL);
    await page.getByRole("button", { name: "View sample review" }).first().click();
    await expect(page.getByText(/sample review could not be loaded right now/)).toBeVisible();
    await expect(page.getByText(/private-server-launch-marker|not-json-launch-marker/)).toHaveCount(
      0,
    );
    recovered = true;
    await page.getByRole("button", { name: "View the sample review" }).click();
    await expect(page.locator("#report-heading")).toBeVisible();
  });
}

test("long finding text and many findings remain searchable and exportable at 320px", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 740 });
  const report = structuredClone(fixtureReport);
  const longToken = "resource_" + "x".repeat(350);
  report.findings = Array.from({ length: 80 }, (_, index) => {
    const item = structuredClone(fixtureReport.findings[0]);
    item.record.finding_id = `launch-long-${index}`;
    item.record.finding = `Launch content ${index} ${longToken} finding ${index}`;
    item.record.evidence = `${longToken} ${"Detailed evidence. ".repeat(250)}`;
    item.record.recommendation = "Recommendation detail. ".repeat(250);
    return item;
  });
  await page.route("**/mock-api/demo", (route) => route.fulfill({ json: report }));
  await page.goto(LIVE_URL);
  await page.getByRole("button", { name: "View sample review" }).first().click();
  await expect(page.locator(".finding-list button")).toHaveCount(80);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
  await page.locator("#finding-search").fill("Launch content 79");
  await expect(page.locator(".finding-list button")).toHaveCount(1);
  await page.locator(".finding-list button").click();
  await expect(page.locator("#finding-detail")).toContainText("finding 79");
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export ledger", exact: true }).click();
  const download = await downloadEvent;
  expect(await download.failure()).toBeNull();
  expect(download.suggestedFilename()).toMatch(/\.json$/);
});
