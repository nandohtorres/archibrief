import { expect, test } from "@playwright/test";
import { LIVE_URL } from "../playwright.config";
import { fixtureReport } from "../lib/fixtures";

for (const theme of ["light", "dark"]) {
  test(`unverified claims stay separate and closed in ${theme} mode`, async ({ page }) => {
    await page.addInitScript((theme) => localStorage.setItem("archibrief-theme", theme), theme);
    await page.route("**/mock-api/**", (route) => route.fulfill({ status: 500, body: "" }));
    await page.route("**/demos/reports/breach-pattern.json", (route) =>
      route.fulfill({
        json: {
          ...fixtureReport,
          unverified_findings: [
            {
              finding_id: "synthetic-unverified",
              finding: "Unconfirmed database claim",
              resource: "aws_db_instance.test",
              evidence: "Unconfirmed evidence",
              reason_code: "wrong_fix",
              reason: "ignored",
              recommendation: "WITHHELD_FIX",
              plain: { action: "WITHHELD_FIX" },
            },
          ],
        },
      }),
    );
    await page.goto(`${LIVE_URL}/?demo=breach-pattern`);
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
    const section = page.locator("details.unable-to-verify");
    await expect(section).toBeVisible();
    await expect(section).not.toHaveAttribute("open", "");
    await section.locator("summary").focus();
    await page.keyboard.press("Enter");
    await expect(section).toHaveAttribute("open", "");
    await expect(section).toContainText("Unconfirmed database claim");
    await expect(section).toContainText("proposed fix did not address");
    await expect(section).toContainText("Recommendation withheld");
    await expect(section.getByRole("button")).toHaveCount(0);
    await expect(page.locator("body")).not.toContainText("WITHHELD_FIX");
    await page.getByRole("tab", { name: /^Stakeholder/ }).click();
    await expect(page.locator("#stakeholder-panel")).not.toContainText(
      "Unconfirmed database claim",
    );
    await page.setViewportSize({ width: 320, height: 720 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
  });
}

test("AI failure is disclosed in the same section", async ({ page }) => {
  await page.route("**/mock-api/**", (route) => route.fulfill({ status: 500, body: "" }));
  await page.route("**/demos/reports/breach-pattern.json", (route) =>
    route.fulfill({
      json: {
        ...fixtureReport,
        analysis_quality: {
          version: 1,
          outcome: "rules-only",
          model_verification: null,
          schema_validation: null,
          reason_codes: ["model_unavailable"],
        },
      },
    }),
  );
  await page.goto(`${LIVE_URL}/?demo=breach-pattern`);
  const section = page.locator("details.unable-to-verify");
  await expect(section.locator("summary")).toContainText("AI analysis did not finish");
  await section.locator("summary").click();
  await expect(section).toContainText("AI analysis failed or timed out");
});

test("saved unsupported chat statements are explicitly labelled", async ({ page }) => {
  await page.route("**/mock-api/**", (route) => route.fulfill({ status: 500, body: "" }));
  await page.route("**/demos/reports/breach-pattern.json", (route) =>
    route.fulfill({ json: fixtureReport }),
  );
  await page.route("**/demos/chats/breach-pattern.json", (route) =>
    route.fulfill({
      json: {
        review_id: fixtureReport.review_id,
        generated_at: "2026-11-16T00:00:00Z",
        suggested: [
          {
            question: "Synthetic question?",
            suggested_id: "synthetic",
            status: "answered",
            refusal_reason: null,
            answer: [{ text: "Cited answer", citations: [] }],
            unsupported: ["UNSUPPORTED_ONLY"],
            model_id: null,
            prompt_version: null,
          },
        ],
      },
    }),
  );
  await page.goto(`${LIVE_URL}/?demo=breach-pattern`);
  await page.getByRole("button", { name: "Synthetic question?", exact: true }).click();
  const note = page.getByLabel("Unsupported answer statements");
  await expect(note).toBeVisible();
  await expect(note).toContainText("UNSUPPORTED_ONLY");
  await expect(note).toContainText("Check them before acting");
  await expect(note.getByRole("link")).toHaveCount(0);
});

test("older schema rejections explain why no claim text is available", async ({ page }) => {
  await page.route("**/mock-api/**", (route) => route.fulfill({ status: 500, body: "" }));
  await page.route("**/demos/reports/breach-pattern.json", (route) =>
    route.fulfill({
      json: {
        ...fixtureReport,
        analysis_quality: {
          version: 1,
          outcome: "partial",
          model_verification: { attempted: 1, accepted: 1, rejected: 0 },
          schema_validation: { attempted: 1, accepted: 0, rejected: 1 },
          reason_codes: ["schema_validation_rejected"],
        },
      },
    }),
  );
  await page.goto(`${LIVE_URL}/?demo=breach-pattern`);
  const section = page.locator("details.unable-to-verify");
  await expect(section).toBeVisible();
  await section.locator("summary").click();
  await expect(section).toContainText("did not save their text");
});
