// Stands in for Cloudflare's Turnstile script, so a test controls whether
// verification succeeds without calling Cloudflare.
import type { Page } from "@playwright/test";

export async function mockTurnstile(page: Page, succeed = true): Promise<void> {
  await page.route("https://challenges.cloudflare.com/**", async (route) => {
    const onload = new URL(route.request().url()).searchParams.get("onload");
    await route.fulfill({
      contentType: "application/javascript",
      body: `
      window.turnstile = {
        render: (element, options) => { setTimeout(() => options[${JSON.stringify(succeed ? "callback" : "error-callback")}]?.(${JSON.stringify(succeed ? "mock-challenge" : "network-error")}), 10); return 'test-widget'; },
        reset: () => {}, remove: () => {}, getResponse: () => 'mock-challenge', isExpired: () => false
      };
      ${onload ? `window[${JSON.stringify(onload)}]?.();` : ""}
    `,
    });
  });
}
