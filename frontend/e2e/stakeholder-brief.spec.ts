import { expect, test } from "@playwright/test";
import { LIVE_URL } from "../playwright.config";

// Stakeholder Brief (ADR-0062) on a saved demo: no prices, severity first,
// keyboard disclosure, phone width and print.
test.describe("Stakeholder Brief", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/mock-api/**", (route) => route.fulfill({ status: 500, body: "" }));
    await page.goto(`${LIVE_URL}/?demo=breach-pattern`);
    await page.getByRole("tab", { name: /^Stakeholder/ }).click();
  });

  test("shows the brief with tiers and no money", async ({ page }) => {
    const panel = page.locator("#stakeholder-panel");
    await expect(
      panel.getByRole("heading", { name: "Stakeholder Brief", exact: true }),
    ).toBeVisible();
    await expect(panel).toContainText("not a new review");
    await expect(panel).toContainText("saved before ArchiBrief recorded review scope");
    await expect(panel).toContainText(
      "Typical overall commitment, not a quote or a verified estimate.",
    );
    const text = await panel.innerText();
    expect(text).not.toMatch(/\$\d|USD \d|per month|engineering time/i);
    // The most serious finding comes first and is open.
    const first = panel.locator("details.brief-row").first();
    await expect(first).toHaveAttribute("open", "");
  });

  test("rows open and close from the keyboard", async ({ page }) => {
    const second = page.locator("#stakeholder-panel details.brief-row").nth(1);
    await expect(second).not.toHaveAttribute("open", "");
    await second.locator("summary").focus();
    await page.keyboard.press("Enter");
    await expect(second).toHaveAttribute("open", "");
    await page.keyboard.press("Space");
    await expect(second).not.toHaveAttribute("open", "");
  });

  test("printing expands every row", async ({ page }) => {
    await page.emulateMedia({ media: "print" });
    await page.evaluate(() => window.dispatchEvent(new Event("beforeprint")));
    const closed = page.locator("#stakeholder-panel details.brief-row:not([open])");
    await expect(closed).toHaveCount(0);
    await page.evaluate(() => window.dispatchEvent(new Event("afterprint")));
    await expect(closed).not.toHaveCount(0);
  });

  test("fits a phone without sideways scrolling", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.locator("#stakeholder-panel details.brief-row").first().scrollIntoViewIfNeeded();
    const widths = await page.evaluate(() => ({
      document: document.documentElement.scrollWidth,
      viewport: window.innerWidth,
    }));
    expect(widths.document).toBeLessThanOrEqual(widths.viewport);
    // On a phone the list comes before any expanded card.
    await page.reload();
    await page.getByRole("tab", { name: /^Stakeholder/ }).click();
    await expect(page.locator("#stakeholder-panel details.brief-row[open]")).toHaveCount(0);
  });

  test("on a narrow phone each row's arrow stays on the severity line", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 700 });
    // A reviewer correction adds a second tag, the case that used to push
    // the arrow onto a line of its own.
    await page.evaluate(() => {
      const tags = document.querySelector("#stakeholder-panel .brief-row-tags");
      const badge = document.createElement("span");
      badge.className = "brief-note-badge";
      badge.textContent = "Reviewer correction";
      tags?.append(badge);
    });
    const offsets = await page.$$eval("#stakeholder-panel details.brief-row > summary", (rows) =>
      rows.map((summary) => {
        const severity = summary.querySelector(".brief-severity")!.getBoundingClientRect();
        const arrow = summary.querySelector("i")!.getBoundingClientRect();
        return Math.abs(arrow.top + arrow.height / 2 - (severity.top + severity.height / 2));
      }),
    );
    expect(offsets.length).toBeGreaterThan(0);
    for (const offset of offsets) expect(offset).toBeLessThan(12);
  });
});
