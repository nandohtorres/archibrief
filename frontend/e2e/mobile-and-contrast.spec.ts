// Basic phone layout and color contrast, in light and dark.
// Runs against the fixture build (no network).
import { expect, test, type Page } from "@playwright/test";
import { FIXTURE_URL, LIVE_URL } from "../playwright.config";
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
  await page.getByRole("button", { name: "See a real review" }).first().click();
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
    // The hero's actions are on the first screen: "See a real review" opens
    // the featured demo, the link goes to the submission form.
    for (const name of [/See a real review/, /Review your own Terraform/]) {
      const action = page
        .locator(".landing-actions")
        .getByRole(name.source.startsWith("See") ? "button" : "link", { name });
      await expect(action).toBeInViewport();
      // WCAG 2.2 target size (minimum) is 24x24 CSS px.
      expect((await action.boundingBox())!.height).toBeGreaterThanOrEqual(24);
    }
    const sample = page.getByRole("button", { name: "See a real review" }).first();
    expect((await sample.boundingBox())!.height).toBeGreaterThanOrEqual(24);
    await openReport(page);
    for (const name of ["Export ledger", "New review"]) {
      const box = await page.getByRole("button", { name }).boundingBox();
      expect(box!.height, name).toBeGreaterThanOrEqual(24);
      expect(box!.width, name).toBeGreaterThanOrEqual(24);
    }
  });

  for (const screen of screens) {
    test(`${screen.name}: every control is at least 24px and inputs don't zoom`, async ({
      page,
    }) => {
      await openInTheme(page, "light");
      await screen.open(page);
      const problems = await page.evaluate(() => {
        const out: string[] = [];
        const controls = document.querySelectorAll<HTMLElement>(
          "button, a[href], input, select, textarea, summary, [role='tab']",
        );
        for (const el of controls) {
          const style = getComputedStyle(el);
          const box = el.getBoundingClientRect();
          if (box.width === 0 || style.visibility === "hidden") continue;
          if (el.closest("details:not([open])") && el.tagName !== "SUMMARY") continue;
          if (el.classList.contains("skip-link")) continue;
          // WCAG 2.5.8 exempts links inside running text.
          const inline = el.tagName === "A" && el.closest("p, li, dd") !== null;
          const label = (el.textContent || el.getAttribute("aria-label") || el.id).trim();
          if (!inline && (box.height < 24 || box.width < 24))
            out.push(
              `small target: ${label.slice(0, 40)} (${Math.round(box.width)}x${Math.round(box.height)})`,
            );
          if (
            ["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName) &&
            parseFloat(style.fontSize) < 16
          )
            out.push(`zooms on focus: ${label.slice(0, 40)} (${style.fontSize})`);
        }
        return out;
      });
      expect(problems).toEqual([]);
    });
  }

  test("header stays compact and finding filters aren't cut off", async ({ page }) => {
    await page.goto(LIVE_URL);
    const header = await page.locator(".site-header").boundingBox();
    expect(header!.height).toBeLessThanOrEqual(150);

    await page.goto(FIXTURE_URL);
    await openReport(page);
    const bounds = await page.locator(".finding-filters").boundingBox();
    for (const chip of await page.locator(".finding-filters button").all()) {
      const box = (await chip.boundingBox())!;
      expect(box.x + box.width).toBeLessThanOrEqual(bounds!.x + bounds!.width + 1);
    }
    const metrics = page.locator(".report-metrics > div");
    const [first, second] = [
      await metrics.nth(0).boundingBox(),
      await metrics.nth(1).boundingBox(),
    ];
    expect(Math.abs(first!.y - second!.y), "summary numbers sit two per row").toBeLessThan(2);
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
