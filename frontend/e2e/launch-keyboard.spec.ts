import { expect, test, type Locator, type Page } from "@playwright/test";
import { FIXTURE_URL } from "../playwright.config";

// Follow actual Tab order: programmatic focus would hide unreachable controls.
async function tabTo(page: Page, target: Locator) {
  for (let i = 0; i < 100; i++) {
    await page.evaluate(() => {
      (window as unknown as { __beforeTab?: Element | null }).__beforeTab = document.activeElement;
    });
    await page.keyboard.press("Tab");
    // Past the last control, a real browser moves focus through its own UI
    // and back to the top of the page. Headless Firefox has no UI, so focus
    // stays put; start again from the top of the document the same way.
    const stuck = await page.evaluate(
      () =>
        document.activeElement ===
        (window as unknown as { __beforeTab?: Element | null }).__beforeTab,
    );
    if (stuck) {
      await page.evaluate(() => {
        document.body.tabIndex = -1;
        document.body.focus();
        document.body.removeAttribute("tabindex");
      });
      await page.keyboard.press("Tab");
    }
    if (await target.evaluate((element) => element === document.activeElement)) {
      await expect(target).toBeInViewport();
      return;
    }
  }
  throw new Error("Control was not reachable within 100 keyboard Tab presses");
}

test("keyboard-only sample, report tabs, filtering, and return to submission", async ({ page }) => {
  await page.goto(FIXTURE_URL);
  await tabTo(page, page.getByRole("button", { name: "See a real review" }).first());
  await page.keyboard.press("Enter");
  await expect(page.locator("#report-heading")).toBeVisible();

  const technical = page.getByRole("tab", { name: /Evidence Dashboard/ });
  const guided = page.getByRole("tab", { name: /Guided Report/ });
  await tabTo(page, technical);
  await page.keyboard.press("ArrowRight");
  await expect(guided).toBeFocused();
  await expect(guided).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("Home");
  await expect(technical).toBeFocused();
  await expect(technical).toHaveAttribute("aria-selected", "true");

  const search = page.locator("#finding-search");
  await tabTo(page, search);
  await page.keyboard.type("no-such-finding-launch-check");
  await expect(page.locator(".finding-list button")).toHaveCount(0);
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.press("Backspace");
  await expect(page.locator(".finding-list button").first()).toBeVisible();
  await tabTo(page, page.getByRole("button", { name: "New review", exact: true }));
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Submit your Terraform" })).toBeVisible();
});
