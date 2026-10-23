// The landing page above the submission flow, and how submissions answer
// when they are paused or refused.
import { expect, test } from "@playwright/test";
import { FIXTURE_URL, LIVE_URL, PUBLIC_URL } from "../playwright.config";
import { fillSubmission } from "./support/submission";
import { mockTurnstile } from "./support/turnstile";

test.describe("landing page", () => {
  test("shows the pitch, the real demos and the full submission form", async ({ page }) => {
    await page.goto(LIVE_URL);
    await expect(page.getByRole("heading", { level: 1 })).toContainText("with the receipts");
    await expect(page.getByRole("heading", { name: "Real reviews of AWS code" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "One review, two readers" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Submit your Terraform" })).toBeVisible();
    // Visitors learn there's a daily limit before they submit; there's no key field.
    await expect(page.locator(".limits-note")).toContainText("a few run each day");
    await expect(page.getByLabel("Admin key")).toHaveCount(0);

    await page.getByRole("link", { name: "Submit your own Terraform" }).click();
    await expect(page).toHaveURL(/#submit$/);
  });

  test("a build without public submissions says so and sends nothing", async ({ page }) => {
    let called = false;
    await page.route("**/mock-api/**", async (route) => {
      called = true;
      await route.fulfill({ status: 500, body: "" });
    });
    await page.goto(LIVE_URL);
    await fillSubmission(page);
    await page.getByRole("button", { name: "Start review" }).click();

    await expect(page.locator(".submit-notice")).toContainText("paused right now");
    expect(called).toBe(false);
    await expect(page.getByRole("heading", { name: "Submit your Terraform" })).toBeVisible();
  });

  test("a refused upload gets a plain message, not an error screen", async ({ page }) => {
    await mockTurnstile(page);
    await page.route("**/mock-api/uploads", (route) =>
      route.fulfill({
        status: 403,
        contentType: "application/json",
        body: '{"error":"challenge_rejected"}',
      }),
    );
    await page.goto(PUBLIC_URL);
    await fillSubmission(page);
    await expect(page.getByRole("button", { name: "Start review" })).toBeEnabled();
    await page.getByRole("button", { name: "Start review" }).click();

    await expect(page.locator(".submit-notice")).toContainText("Verification expired");
    await expect(page.getByText("challenge_rejected")).toHaveCount(0);
  });

  test("the hero button opens a review at the top of the page", async ({ page }) => {
    await page.goto(FIXTURE_URL);
    await page.getByRole("button", { name: "See a real review" }).click();
    await expect(page.locator("#report-heading")).toBeVisible();
    // Opened from far down the page, the report still starts at the top.
    await expect(page.locator("#report-heading")).toBeInViewport();
    expect(await page.evaluate(() => window.scrollY)).toBeLessThan(50);
  });

  test("the logo goes back to the home page from a report", async ({ page }) => {
    await page.goto(LIVE_URL);
    await page.getByRole("button", { name: "See a real review" }).click();
    await expect(page.locator("#report-heading")).toBeVisible();
    await page.getByRole("button", { name: "ArchiBrief home" }).click();
    await expect(page.getByRole("heading", { level: 1 })).toContainText("with the receipts");
    await expect(page.locator("#report-heading")).toHaveCount(0);
    expect(await page.evaluate(() => window.scrollY)).toBeLessThan(50);
  });

  test("a header link opens its home page section from a report", async ({ page }) => {
    await page.goto(LIVE_URL);
    await page.getByRole("button", { name: "See a real review" }).click();
    await expect(page.locator("#report-heading")).toBeVisible();
    await page.getByRole("navigation", { name: "Sections" }).getByText("How it works").click();
    await expect(page.locator("#report-heading")).toHaveCount(0);
    await expect(page.locator("#how-heading")).toBeInViewport();
  });
});
