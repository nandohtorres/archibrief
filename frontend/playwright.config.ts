import { defineConfig } from "@playwright/test";

// Two static sites are served because `output: "export"` inlines
// NEXT_PUBLIC_API_BASE_URL at build time - each webServer entry below
// builds its own variant and serves it; see e2e/dev-server.mjs for why
// build+serve are one self-contained script per variant rather than a
// separate build step.
export const FIXTURE_URL = "http://127.0.0.1:4310";
export const LIVE_URL = "http://127.0.0.1:4311";
export const PUBLIC_URL = "http://127.0.0.1:4312";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [[process.env.CI ? "github" : "list"], ["html", { open: "never" }]],
  use: {
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "node e2e/dev-server.mjs public",
      url: PUBLIC_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: "node e2e/dev-server.mjs fixture",
      url: FIXTURE_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: "node e2e/dev-server.mjs live",
      url: LIVE_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
