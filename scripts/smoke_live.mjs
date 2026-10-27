// Read-only production checks. Every network request is explicitly GET.
import { randomUUID } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as sleep } from "node:timers/promises";

function origin(value) {
  const url = new URL(value);
  if (
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    url.pathname !== "/"
  ) {
    throw new Error(
      "Use HTTPS site/API origins without credentials, paths or query strings",
    );
  }
  return url.origin;
}

function requireValue(condition, message) {
  if (!condition) throw new Error(message);
}

export function checkSecurityHeaders(headers) {
  requireValue(
    headers.get("x-content-type-options")?.toLowerCase() === "nosniff",
    "missing nosniff",
  );
  requireValue(
    headers.get("x-frame-options")?.toUpperCase() === "DENY",
    "missing frame DENY",
  );
  requireValue(
    headers.get("referrer-policy") === "strict-origin-when-cross-origin",
    "unexpected referrer policy",
  );
  const hsts = headers.get("strict-transport-security") ?? "";
  requireValue(
    Number(hsts.match(/max-age\s*=\s*(\d+)/i)?.[1]) >= 31536000 &&
      /\bincludeSubDomains\b/i.test(hsts) &&
      /\bpreload\b/i.test(hsts),
    "incomplete HSTS",
  );
  const directives = new Map(
    (headers.get("content-security-policy") ?? "").split(";").map((part) => {
      const [name, ...values] = part.trim().split(/\s+/);
      return [name, values];
    }),
  );
  for (const [name, value] of [
    ["default-src", "'self'"],
    ["object-src", "'none'"],
    ["base-uri", "'self'"],
    ["frame-ancestors", "'none'"],
  ]) {
    requireValue(
      directives.get(name)?.join(" ") === value,
      `unexpected CSP ${name}`,
    );
  }
  for (const name of [
    "script-src",
    "style-src",
    "font-src",
    "img-src",
    "connect-src",
    "frame-src",
  ]) {
    requireValue(
      directives.has(name) && !directives.get(name).includes("*"),
      `missing or unrestricted CSP ${name}`,
    );
  }
}

export async function smokeLive(
  siteUrl,
  apiUrl,
  expectedRevision,
  {
    fetchImpl = fetch,
    wait = sleep,
    now = Date.now,
    log = console.log,
    revisionTimeoutMs = 180_000,
    requestTimeoutMs = 10_000,
  } = {},
) {
  const site = origin(siteUrl),
    api = origin(apiUrl);
  requireValue(
    !expectedRevision || /^[a-f0-9]{40}$/.test(expectedRevision),
    "Expected revision must be a full lowercase commit SHA",
  );
  const results = [];
  async function get(url) {
    return fetchImpl(url, {
      method: "GET",
      redirect: "error",
      headers: { Origin: site, "Cache-Control": "no-cache" },
      signal: AbortSignal.timeout(requestTimeoutMs),
    });
  }
  async function check(name, run) {
    try {
      const detail = await run();
      results.push({ name, ok: true, detail });
      log(`PASS ${name}: ${detail}`);
    } catch (error) {
      const detail = String(error.message).replace(/[\r\n]/g, " ");
      results.push({ name, ok: false, detail });
      log(`FAIL ${name}: ${detail}`);
    }
  }
  await check("homepage and security headers", async () => {
    const response = await get(`${site}/`);
    requireValue(
      response.status === 200,
      `HTTP ${response.status}, expected 200`,
    );
    requireValue(
      /<title[^>]*>[^<]*ArchiBrief/i.test(await response.text()),
      "app title missing from HTML",
    );
    checkSecurityHeaders(response.headers);
    return "200; ArchiBrief title; CSP, HSTS, frame, content-type and referrer protections";
  });
  await check("build revision", async () => {
    const deadline = now() + (expectedRevision ? revisionTimeoutMs : 0);
    let delay = 2_000;
    for (;;) {
      try {
        const response = await get(`${site}/build-info.json`);
        requireValue(
          response.status === 200,
          `HTTP ${response.status}, expected 200`,
        );
        const info = await response.json();
        requireValue(
          info?.schema_version === "frontend-build@1" &&
            /^[a-f0-9]{64}$/.test(info.index_sha256) &&
            Number.isFinite(Date.parse(info.built_at)),
          "invalid build-info.json",
        );
        requireValue(
          info.source_revision === null ||
            /^[a-f0-9]{40}$/.test(info.source_revision),
          "invalid source_revision",
        );
        requireValue(
          !expectedRevision || info.source_revision === expectedRevision,
          `revision ${info.source_revision ?? "unrecorded"}, expected ${expectedRevision}`,
        );
        return (
          info.source_revision ??
          "valid metadata; revision unrecorded (manual build)"
        );
      } catch (error) {
        const remaining = deadline - now();
        if (!expectedRevision || remaining <= 0) throw error;
        await wait(Math.min(delay, remaining));
        delay = Math.min(delay * 2, 20_000);
      }
    }
  });
  await check("site icon", async () => {
    const response = await get(`${site}/icon.svg`);
    requireValue(
      response.status === 200,
      `HTTP ${response.status}, expected 200`,
    );
    requireValue(
      (await response.text()).includes("<svg"),
      "response is not an SVG",
    );
    return "200; SVG available";
  });
  await check("demo asset", async () => {
    const response = await get(`${site}/demos/reports/breach-pattern.json`);
    requireValue(
      response.status === 200,
      `HTTP ${response.status}, expected 200`,
    );
    requireValue(
      typeof (await response.json()) === "object",
      "demo is not JSON",
    );
    return "200; demo report JSON available";
  });
  await check("API missing review", async () => {
    const response = await get(`${api}/reviews/${randomUUID()}`);
    requireValue(
      response.status === 404,
      `HTTP ${response.status}, expected handler 404`,
    );
    requireValue(
      (await response.json()).error === "review not found",
      "404 is not the get_review handler response",
    );
    return "404; get_review returned review not found";
  });
  return results;
}

if (
  process.argv[1] &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  try {
    if (process.argv.length < 4 || process.argv.length > 5)
      throw new Error(
        "Usage: node scripts/smoke_live.mjs <site-url> <api-url> [expected-revision]",
      );
    const results = await smokeLive(...process.argv.slice(2));
    if (results.some((result) => !result.ok)) process.exitCode = 1;
  } catch (error) {
    console.error(`FAIL configuration: ${error.message}`);
    process.exitCode = 1;
  }
}
