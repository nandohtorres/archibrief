// Item #8: landing page (design option A) above the submission flow, and
// owner-only submissions until public submissions open (ADR-0047).
import { expect, test } from "@playwright/test";
import { FIXTURE_URL, LIVE_URL } from "../playwright.config";

test.describe("landing page", () => {
  test("shows the pitch, samples and the full submission form", async ({ page }) => {
    await page.goto(LIVE_URL);
    await expect(page.getByRole("heading", { level: 1 })).toContainText("with the receipts");
    await expect(page.getByRole("heading", { name: "Sample reviews" })).toBeVisible();
    await expect(page.getByText("Coming soon", { exact: true }).first()).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Review an existing AWS architecture" }),
    ).toBeVisible();
    await expect(page.getByLabel("Admin key")).toBeVisible();

    await page.getByRole("link", { name: "Review your own Terraform" }).click();
    await expect(page).toHaveURL(/#submit$/);
  });

  test("without the owner key, submitting explains it's owner-only and sends nothing", async ({
    page,
  }) => {
    let called = false;
    await page.route("**/mock-api/**", async (route) => {
      called = true;
      await route.fulfill({ status: 500, body: "" });
    });
    await page.goto(LIVE_URL);
    await page.getByRole("button", { name: /Detailed \(complex, cross-checked\)/ }).click();
    await page.getByRole("button", { name: "Submit to deployed API" }).click();

    await expect(page.locator(".submit-notice")).toContainText("limited to the site owner");
    expect(called).toBe(false);
    await expect(
      page.getByRole("heading", { name: "Review an existing AWS architecture" }),
    ).toBeVisible();
  });

  test("a rejected key gets a plain message, not an error screen", async ({ page }) => {
    await page.route("**/mock-api/uploads", (route) =>
      route.fulfill({
        status: 401,
        contentType: "application/json",
        body: '{"message":"Unauthorized"}',
      }),
    );
    await page.goto(LIVE_URL);
    await page.getByLabel("Admin key").fill("wrong-key");
    await page.getByRole("button", { name: /Detailed \(complex, cross-checked\)/ }).click();
    await page.getByRole("button", { name: "Submit to deployed API" }).click();

    await expect(page.locator(".submit-notice")).toContainText("That key wasn't accepted");
    await expect(page.getByText("Unauthorized")).toHaveCount(0);
  });

  test("the sample card opens the sample review", async ({ page }) => {
    await page.goto(FIXTURE_URL);
    await page.getByRole("button", { name: "Open sample review" }).click();
    await expect(page.locator("#report-heading")).toBeVisible();
    // Opened from far down the page, the report still starts at the top.
    await expect(page.locator("#report-heading")).toBeInViewport();
    expect(await page.evaluate(() => window.scrollY)).toBeLessThan(50);
  });
});
