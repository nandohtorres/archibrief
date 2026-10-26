import { expect, test } from "@playwright/test";
import { LIVE_URL } from "../playwright.config";
import { fixtureReport } from "../lib/fixtures";

test("risk, action and partial quality stay independent of evidence type", async ({ page }) => {
  const [rule, fact] = [fixtureReport.findings[0], fixtureReport.findings[4]];
  await page.route("**/demos/demos.json", (route) => route.fulfill({ status: 404, body: "" }));
  await page.route("**/mock-api/demo", (route) =>
    route.fulfill({
      json: {
        ...fixtureReport,
        analysis_scope: {
          version: "terraform-observations@2026-10-23",
          facts_emitted: 30,
          omitted_resources: 2,
          omitted_items: 0,
          incomplete_resources: 1,
          truncated: true,
          runtime_verified: false,
        },
        findings: [
          {
            ...rule,
            assessment: { version: 1, severity: "medium", action: "needed", source: "rule" },
          },
          {
            ...fact,
            record: { ...fact.record, finding: "A critical risk classified as a fact" },
            assessment: { version: 1, severity: "critical", action: "needed", source: "model" },
          },
        ],
        analysis_quality: {
          version: 1,
          outcome: "partial",
          model_verification: { attempted: 3, accepted: 2, rejected: 1 },
          schema_validation: { attempted: 3, accepted: 2, rejected: 1 },
          reason_codes: ["model_verification_rejected", "schema_validation_rejected"],
        },
      },
    }),
  );
  await page.goto(LIVE_URL);
  await page.getByRole("button", { name: "See a real review" }).first().click();
  await expect(page.getByLabel("Analysis quality")).toContainText("Analysis is partial");
  await expect(page.getByLabel("Analysis quality")).toContainText(
    "missing details do not establish absence",
  );
  await expect(page.getByLabel("Analysis quality")).toContainText(
    "Some expressions could not be checked",
  );
  await expect(page.getByLabel("Analysis quality")).toContainText("2 of 3 retained, 1 rejected");
  await expect(page.locator(".finding-list button").first()).toContainText(
    "A critical risk classified as a fact",
  );
  await page.getByRole("button", { name: "critical risk", exact: true }).click();
  await expect(page.locator(".finding-list > li")).toHaveCount(1);
  await expect(page.locator("#finding-detail")).toContainText("Critical risk · model");
  await expect(page.locator("#finding-detail")).toContainText("Reported fact");
  await page.getByRole("button", { name: "medium risk", exact: true }).click();
  await expect(page.locator(".finding-list > li")).toHaveCount(1);
  await expect(page.locator("#finding-detail")).toContainText("Medium risk · rule");
});
