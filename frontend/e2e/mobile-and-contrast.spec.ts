// Item #9: basic phone layout and color contrast, in light and dark.
// Runs against the fixture build (no network). This is the baseline
// check, not the full mobile UI pass, which is still to come.
import { expect, test, type Page } from "@playwright/test";
import { FIXTURE_URL } from "../playwright.config";
import { findContrastFailures } from "./support/contrast";

const PHONE = { width: 390, height: 844 };
const THEMES = ["light", "dark"] as const;

// Boots the page already in the given theme (stored choice, like a
// returning visitor). Switching themes mid-test through the select was
// flaky in headless Chrome: a few elements kept the old theme's colors.
async function openInTheme(page: Page, theme: (typeof THEMES)[number]) {
  await page.addInitScript((choice) => {
    window.localStorage.setItem("archibrief-theme", choice);
  }, theme);
  await page.goto(FIXTURE_URL);
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
  await expect
    .poll(() => page.evaluate(() => getComputedStyle(document.body).backgroundColor))
    .toBe(theme === "dark" ? "rgb(13, 19, 25)" : "rgb(244, 247, 249)");
}

async function openReport(page: Page) {
  await page.getByRole("button", { name: "View sample review" }).first().click();
  await expect(page.locator("#report-heading")).toBeVisible();
}

async function horizontalOverflow(page: Page) {
  return page.evaluate(() => {
    const viewport = document.documentElement.clientWidth;
    const clipped = (el: Element) => {
      for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
        const overflowX = getComputedStyle(p).overflowX;
        if (overflowX === "auto" || overflowX === "scroll" || overflowX === "hidden") return true;
      }
      return false;
    };
    const offenders = [...document.querySelectorAll<HTMLElement>("body *")]
      .filter((el) => {
        const box = el.getBoundingClientRect();
        if (box.width === 0 || clipped(el)) return false;
        return box.right > viewport + 1 || box.left < -1;
      })
      .slice(0, 5)
      .map((el) => `${el.tagName.toLowerCase()}.${String(el.className)}`.slice(0, 80));
    return { scrollWidth: document.documentElement.scrollWidth, viewport, offenders };
  });
}

const screens: Array<{ name: string; open: (page: Page) => Promise<void> }> = [
  { name: "submission", open: async () => {} },
  { name: "report (technical)", open: openReport },
  {
    name: "report (guided)",
    open: async (page) => {
      await openReport(page);
      await page.getByRole("tab", { name: /Guided Report/ }).click();
    },
  },
];

test.describe("phone layout at 390px", () => {
  test.use({ viewport: PHONE, hasTouch: true, isMobile: true });

  for (const screen of screens) {
    for (const theme of THEMES) {
      test(`${screen.name} (${theme}) has no horizontal scroll`, async ({ page }) => {
        await openInTheme(page, theme);
        await screen.open(page);
        const result = await horizontalOverflow(page);
        expect(result.offenders, "elements past the right edge").toEqual([]);
        expect(result.scrollWidth).toBeLessThanOrEqual(result.viewport);
      });
    }
  }

  test("main actions are visible and large enough to tap", async ({ page }) => {
    await page.goto(FIXTURE_URL);
    const sample = page.getByRole("button", { name: "View sample review" }).first();
    await expect(sample).toBeInViewport();
    // WCAG 2.2 target size (minimum) is 24x24 CSS px.
    expect((await sample.boundingBox())!.height).toBeGreaterThanOrEqual(24);
    await openReport(page);
    for (const name of ["Export ledger", "New review"]) {
      const box = await page.getByRole("button", { name }).boundingBox();
      expect(box!.height, name).toBeGreaterThanOrEqual(24);
      expect(box!.width, name).toBeGreaterThanOrEqual(24);
    }
  });
});

test("the theme select switches the page theme", async ({ page }) => {
  await page.goto(FIXTURE_URL);
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Theme").selectOption("dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByLabel("Theme").selectOption("light");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test.describe("color contrast (WCAG AA)", () => {
  test("the checker itself flags low contrast, including SVG text", async ({ page }) => {
    await page.setContent(`
      <body style="background:#fff">
        <p style="color:#999">too light</p>
        <p style="color:#222">fine</p>
        <details><summary style="color:#222">open me</summary><p style="color:#eee">hidden</p></details>
        <svg width="200" height="60"><g>
          <rect width="200" height="60" style="fill:#333"></rect>
          <text x="10" y="35" style="fill:#555;font-size:14px">dim label</text>
        </g></svg>
      </body>`);
    const failures = await findContrastFailures(page);
    expect(failures.map((f) => f.text).sort()).toEqual(["dim label", "too light"]);
  });

  const viewports = [
    { label: "desktop", size: { width: 1280, height: 900 } },
    { label: "phone", size: PHONE },
  ];
  for (const viewport of viewports) {
    for (const screen of screens) {
      for (const theme of THEMES) {
        test(`${screen.name} ${viewport.label} ${theme}`, async ({ page }) => {
          await page.setViewportSize(viewport.size);
          await openInTheme(page, theme);
          await screen.open(page);
          expect(await findContrastFailures(page)).toEqual([]);
        });
      }
    }
  }
});
