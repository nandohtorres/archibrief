import { createRequire } from "node:module";
import { expect, test } from "@playwright/test";
import { FIXTURE_URL } from "../playwright.config";

// axe-core is already locked through Lighthouse; do not fetch a browser script.
// API/tags: https://www.deque.com/axe/core-documentation/api-documentation/
const resolveDependency = createRequire(__filename);
const axePath = resolveDependency.resolve("axe-core/axe.min.js");

for (const theme of ["light", "dark"] as const) {
  for (const screen of ["landing", "technical", "guided"] as const) {
    test(`axe WCAG A/AA: ${screen}, ${theme}`, async ({ page }, testInfo) => {
      await page.emulateMedia({ reducedMotion: "reduce", colorScheme: theme });
      await page.addInitScript((value) => localStorage.setItem("archibrief-theme", value), theme);
      await page.goto(FIXTURE_URL);
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
      if (screen !== "landing") {
        await page.getByRole("button", { name: "See a real review" }).first().click();
        await expect(page.locator("#report-heading")).toBeVisible();
        if (screen === "guided") {
          await page.getByRole("tab", { name: /Guided Report/ }).click();
        }
      }
      await page.evaluate(() => document.fonts.ready);
      await page.addScriptTag({ path: axePath });
      const results = await page.evaluate(async () => {
        const axe = (window as unknown as { axe: typeof import("axe-core") }).axe;
        return axe.run(document, {
          runOnly: {
            type: "tag",
            values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"],
          },
        });
      });
      await testInfo.attach("axe-results", {
        body: JSON.stringify(results, null, 2),
        contentType: "application/json",
      });
      expect(
        results.violations.map(({ id, nodes }) => ({
          id,
          targets: nodes.map((node) => node.target),
        })),
      ).toEqual([]);
    });
  }
}
