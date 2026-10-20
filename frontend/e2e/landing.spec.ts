// The landing page above the submission flow, and
// owner-only submissions until public submissions open (ADR-0047).
import { expect, test } from "@playwright/test";
import { FIXTURE_URL, LIVE_URL } from "../playwright.config";

test.describe("landing page", () => {
  test("shows the pitch, the real demos and the full submission form", async ({ page }) => {
    await page.goto(LIVE_URL);
    await expect(page.getByRole("heading", { level: 1 })).toContainText("why it matters");
    await expect(
      page.getByRole("heading", { name: "Real reviews of real public code" }),
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: "One review, two readers" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Review your own Terraform" })).toBeVisible();
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
    await page.getByRole("button", { name: /Payments platform/ }).click();
    await page.getByRole("button", { name: "Start review" }).click();

    await expect(page.locator(".submit-notice")).toContainText("limited to the site owner");
    expect(called).toBe(false);
    await expect(page.getByRole("heading", { name: "Review your own Terraform" })).toBeVisible();
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
    await page.getByRole("button", { name: /Payments platform/ }).click();
    await page.getByRole("button", { name: "Start review" }).click();

    await expect(page.locator(".submit-notice")).toContainText("That key wasn't accepted");
    await expect(page.getByText("Unauthorized")).toHaveCount(0);
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
    await expect(page.getByRole("heading", { level: 1 })).toContainText("why it matters");
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
