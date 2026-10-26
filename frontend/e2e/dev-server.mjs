// Builds one static-export variant and serves it, as a single process
// Playwright's webServer config can start/stop directly - deliberately
// not split into a separate build step, since relying on Playwright's
// globalSetup running strictly before webServer startup isn't a
// documented guarantee.
//
// `output: "export"` (frontend/next.config.ts) inlines
// NEXT_PUBLIC_API_BASE_URL at build time, so the no-API fixture/demo
// critical path and the admin-gated "live" critical path (network
// calls intercepted via Playwright route mocking - see
// live-admin-path.spec.ts - never real AWS) each need their own build.
// Each variant gets its own `distDir` (next.config.ts) - confirmed
// experimentally that with a non-default distDir, Next exports the
// static site directly INTO that directory rather than into a separate
// sibling `out/` (that's only where it lands with the default ".next"
// distDir), so the distDir name doubles as the final served directory -
// no separate build-then-rename step needed.
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { runLoggedCommand } from "./build-log.mjs";

const FRONTEND_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const variant = process.argv[2];
const variants = {
  fixture: { outDir: "out-fixture", port: 4310, apiBaseUrl: "" },
  // Same-origin as the static site itself, so fetches never leave the
  // page's own origin - only Playwright's page.route() interception in
  // live-admin-path.spec.ts ever answers them.
  live: { outDir: "out-live", port: 4311, apiBaseUrl: "/mock-api" },
  public: { outDir: "out-public", port: 4312, apiBaseUrl: "/mock-api" },
};

const config = variants[variant];
if (!config) {
  throw new Error(
    `Unknown E2E server variant ${JSON.stringify(variant)} (expected "fixture" or "live")`,
  );
}

runLoggedCommand({
  command: "npm",
  args: ["run", "build:e2e"],
  cwd: FRONTEND_DIR,
  logFile: path.join(FRONTEND_DIR, "e2e-build-logs", `${variant}.log`),
  shell: process.platform === "win32",
  env: {
    ...process.env,
    NEXT_DIST_DIR: config.outDir,
    NEXT_PUBLIC_API_BASE_URL: config.apiBaseUrl,
    NEXT_PUBLIC_PUBLIC_ACCESS_ENABLED: variant === "public" ? "true" : "false",
    NEXT_PUBLIC_TURNSTILE_SITE_KEY: variant === "public" ? "1x00000000000000000000AA" : "",
  },
});

const indexHtml = path.join(FRONTEND_DIR, config.outDir, "index.html");
if (!existsSync(indexHtml)) {
  throw new Error(`next build did not produce ${indexHtml} for variant ${variant}`);
}

// `--build-only` stops here (used by `npm run lighthouse`, where Lighthouse
// CI serves the built directory itself).
if (process.argv.includes("--build-only")) process.exit(0);

const result = spawnSync("npx", ["serve", config.outDir, "-s", "-l", String(config.port)], {
  cwd: FRONTEND_DIR,
  stdio: "inherit",
  shell: process.platform === "win32",
  windowsHide: true,
});
process.exit(result.status ?? 1);
