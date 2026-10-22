// Renders the social preview image (public/og-image.png, 1200x630) that
// link previews show when the site is shared. Rebuild it after changing
// the landing headline:
//
//   cd frontend && node scripts/build-og-image.mjs
//
// Uses the Playwright Chromium the e2e tests already install. Fonts load
// from Google Fonts, so it needs network access.
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const OUT = fileURLToPath(new URL("../public/og-image.png", import.meta.url));

const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;700&family=Source+Serif+4:ital,opsz,wght@0,8..60,600;1,8..60,500&display=swap" rel="stylesheet">
<style>
  html, body { margin: 0; }
  body {
    width: 1200px; height: 630px; box-sizing: border-box;
    padding: 72px 88px;
    display: flex; flex-direction: column; justify-content: space-between;
    background-color: #0e131a;
    background-image: radial-gradient(rgba(255,255,255,0.07) 1px, transparent 1px);
    background-size: 22px 22px;
    color: #e8eef3;
  }
  .brand { display: flex; align-items: center; gap: 16px; }
  .brand svg { width: 52px; height: 52px; color: #7cc0dc; }
  .brand strong { font: 700 30px/1 "IBM Plex Mono", monospace; letter-spacing: -0.01em; }
  .brand span { display: block; margin-top: 8px; color: #9fb1c0; font: 500 17px/1 "IBM Plex Mono", monospace; }
  h1 { margin: 0; max-width: 980px; font: 600 70px/1.08 "Source Serif 4", Georgia, serif; letter-spacing: -0.015em; }
  h1 em { color: #7cc0dc; font-weight: 500; }
  ul { display: flex; gap: 36px; margin: 0; padding: 0; list-style: none; color: #b8c6d2; font: 500 19px/1 "IBM Plex Mono", monospace; white-space: nowrap; }
  li::before { content: "✓"; margin-right: 10px; color: #5fcf9f; }
</style>
</head>
<body>
  <div class="brand">
    <svg viewBox="0 0 32 32" aria-hidden="true">
      <path d="M16 3 29 10 16 17 3 10Z" fill="currentColor"/>
      <path d="M3 15.5 16 22.5 29 15.5" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linejoin="round" opacity="0.65"/>
      <path d="M3 21 16 28 29 21" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linejoin="round" opacity="0.35"/>
    </svg>
    <div><strong>ArchiBrief</strong><span>Your AWS architecture, briefed</span></div>
  </div>
  <h1>A second opinion on your AWS architecture, <em>with the receipts.</em></h1>
  <ul>
    <li>Never touches your AWS account</li>
    <li>Evidence with each finding</li>
    <li>AI mistakes shown</li>
  </ul>
</body>
</html>`;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 630 } });
await page.setContent(html, { waitUntil: "networkidle" });
await page.evaluate(() => document.fonts.ready);
await page.screenshot({ path: OUT });
await browser.close();
console.log(`wrote ${OUT}`);
