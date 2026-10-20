import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  reactStrictMode: true,
  // Overridable so the E2E harness can build the fixture-mode and
  // live-mode variants (different NEXT_PUBLIC_API_BASE_URL, both
  // inlined at build time) without the two `next build` runs
  // clobbering each other's cache — see tests/e2e/global-setup.ts.
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
