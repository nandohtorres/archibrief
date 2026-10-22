// Fills the submission form with a real bundled Terraform archive and a
// brief, the way a visitor would (upload + type), so a test can go
// straight to "Start review".
import path from "node:path";
import type { Page } from "@playwright/test";

export const SAMPLE_ARCHIVE = path.resolve(__dirname, "../../public/fixtures/preset-detailed.tar");

export async function fillSubmission(page: Page): Promise<void> {
  await page.locator("#terraform-archive").setInputFiles(SAMPLE_ARCHIVE);
  await page
    .getByLabel("Workload brief")
    .fill(
      "Customer payments platform processing roughly 500 requests/second at peak. Must meet PCI-DSS; requires 99.95% availability.",
    );
}
