import { defineConfig } from "@playwright/test";

// Two static sites are served because `output: "export"` inlines
// NEXT_PUBLIC_API_BASE_URL at build time - each webServer entry below
// builds its own variant and serves it; see e2e/dev-server.mjs for why
// build+serve are one self-contained script per variant rather than a
// separate build step.
// Separate worktrees can run checks concurrently without reusing each other's site.
const PORT_BASE = Number(process.env.ARCHIBRIEF_E2E_PORT_BASE ?? 4310);
if (!Number.isInteger(PORT_BASE) || PORT_BASE < 1024 || PORT_BASE > 65533) {
  throw new Error("ARCHIBRIEF_E2E_PORT_BASE must be an integer from 1024 to 65533");
}
export const FIXTURE_URL = `http://127.0.0.1:${PORT_BASE}`;
export const LIVE_URL = `http://127.0.0.1:${PORT_BASE + 1}`;
export const PUBLIC_URL = `http://127.0.0.1:${PORT_BASE + 2}`;

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
