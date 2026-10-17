import { expect, test } from "@playwright/test";
import { FIXTURE_URL } from "../playwright.config";

for (const viewport of [
  { width: 320, height: 568 },
  { width: 768, height: 1024 },
  { width: 844, height: 390 },
  { width: 1920, height: 1080 },
]) {
  test(`landing and both report views fit ${viewport.width}x${viewport.height}`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.goto(FIXTURE_URL);
    const assertFits = async () => {
      expect(
        await page.evaluate(() => ({
          document: document.documentElement.scrollWidth,
          viewport: document.documentElement.clientWidth,
        })),
      ).toEqual({ document: viewport.width, viewport: viewport.width });
    };
    await assertFits();
    await page.getByRole("button", { name: "View sample review" }).first().click();
    await expect(page.locator("#report-heading")).toBeVisible();
    await assertFits();
    await page.getByRole("button", { name: "Export ledger", exact: true }).scrollIntoViewIfNeeded();
    await expect(page.getByRole("button", { name: "Export ledger", exact: true })).toBeInViewport();
    await page.getByRole("tab", { name: /Guided Report/ }).click();
    await expect(page.locator("#stakeholder-panel")).toBeVisible();
    await assertFits();
  });
}
