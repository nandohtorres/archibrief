// Item #8: landing page (design option A) above the submission flow.
import { expect, test } from "@playwright/test";
import { FIXTURE_URL, LIVE_URL } from "../playwright.config";

test.describe("landing page", () => {
  test("public visitors see the pitch and samples, not the admin form", async ({ page }) => {
    await page.goto(LIVE_URL);
    await expect(page.getByRole("heading", { level: 1 })).toContainText("with the receipts");
    await expect(page.getByRole("heading", { name: "Sample reviews" })).toBeVisible();
    await expect(page.getByText("Coming soon", { exact: true }).first()).toBeVisible();
    await expect(page.getByLabel("Admin key")).toHaveCount(0);
    await expect(
      page.getByRole("heading", { name: "Public submissions are opening soon" }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Submit to deployed API" })).toHaveCount(0);

    await page.getByRole("link", { name: "Review your own Terraform" }).click();
    await expect(page).toHaveURL(/#submit$/);
  });

  test("?admin shows the key field and the real submission form", async ({ page }) => {
    await page.goto(`${LIVE_URL}/?admin`);
    await expect(page.getByLabel("Admin key")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Review an existing AWS architecture" }),
    ).toBeVisible();
  });

  test("the sample card opens the sample review", async ({ page }) => {
    await page.goto(FIXTURE_URL);
    await page.getByRole("button", { name: "Open sample review" }).click();
    await expect(page.locator("#report-heading")).toBeVisible();
  });
});
