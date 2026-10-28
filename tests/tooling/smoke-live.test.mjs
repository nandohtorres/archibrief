import assert from "node:assert/strict";
import { test } from "node:test";
import { smokeLive } from "../../scripts/smoke_live.mjs";

const revision = "a".repeat(40);
const metadata = (sha = revision) => ({
  schema_version: "frontend-build@1",
  source_revision: sha,
  built_at: "2026-10-27T00:00:00Z",
  index_sha256: "b".repeat(64),
});
const headers = {
  "x-content-type-options": "nosniff",
  "x-frame-options": "DENY",
  "referrer-policy": "strict-origin-when-cross-origin",
  "strict-transport-security": "max-age=31536000; includeSubDomains; preload",
  "content-security-policy":
    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'self'; frame-src https://challenges.cloudflare.com; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
};
function healthy(url) {
  const path = new URL(url).pathname;
  if (path === "/")
    return new Response("<title>ArchiBrief · Architecture review</title>", {
      headers,
    });
  if (path === "/build-info.json") return Response.json(metadata());
  if (path === "/icon.svg") return new Response("<svg></svg>");
  if (path.startsWith("/demos/")) return Response.json({ title: "Demo" });
  assert.match(path, /^\/reviews\/[a-f0-9-]{36}$/);
  return Response.json({ error: "review not found" }, { status: 404 });
}
const run = (fetchImpl, extra = {}) =>
  smokeLive("https://site.test", "https://api.test", undefined, {
    fetchImpl,
    log() {},
    ...extra,
  });

test("live smoke sends only GETs, no body, and the site Origin; reports each check", async () => {
  const calls = [],
    lines = [];
  const results = await run(
    async (url, options) => {
      calls.push(url);
      assert.equal(options.method, "GET");
      assert.equal(options.body, undefined);
      assert.equal(options.headers.Origin, "https://site.test");
      assert.equal(options.redirect, "error");
      return healthy(url);
    },
    { log: (line) => lines.push(line) },
  );
  assert.equal(calls.length, 5);
  assert.equal(
    results.every((result) => result.ok),
    true,
  );
  assert.equal(lines.length, 5);
  assert.equal(
    lines.every((line) => line.startsWith("PASS ")),
    true,
  );
});

test("missing headers, HTML masquerading as JSON and API failures fail independently", async () => {
  for (const status of [403, 500]) {
    const results = await run(async (url) => {
      if (new URL(url).pathname === "/")
        return new Response("<title>ArchiBrief</title>");
      if (url.includes("/demos/")) return new Response("<html>fallback</html>");
      if (url.includes("/reviews/")) return new Response("blocked", { status });
      return healthy(url);
    });
    assert.deepEqual(
      results.map((result) => result.ok),
      [false, true, true, false, false],
    );
  }
});

test("a gateway 404 or network timeout is not a successful Lambda smoke", async () => {
  for (const reply of [
    () => new Response("not found", { status: 404 }),
    () => {
      throw new Error("request timed out");
    },
  ]) {
    const results = await run(async (url) =>
      url.includes("/reviews/") ? reply() : healthy(url),
    );
    assert.equal(results.at(-1).ok, false);
    assert.equal(
      results.slice(0, -1).every((result) => result.ok),
      true,
    );
  }
});

test("revision verification retries a stale edge response then succeeds", async () => {
  let elapsed = 0,
    attempts = 0;
  const results = await smokeLive(
    "https://site.test",
    "https://api.test",
    revision,
    {
      fetchImpl: async (url) =>
        url.endsWith("/build-info.json")
          ? Response.json(metadata(++attempts < 3 ? "c".repeat(40) : revision))
          : healthy(url),
      now: () => elapsed,
      wait: async (ms) => {
        elapsed += ms;
      },
      log() {},
    },
  );
  assert.equal(attempts, 3);
  assert.equal(elapsed, 6000);
  assert.equal(
    results.every((result) => result.ok),
    true,
  );
});

test("revision retries stop at three minutes and still run remaining checks", async () => {
  let elapsed = 0;
  const results = await smokeLive(
    "https://site.test",
    "https://api.test",
    "c".repeat(40),
    {
      fetchImpl: async (url) => healthy(url),
      now: () => elapsed,
      wait: async (ms) => {
        elapsed += ms;
      },
      log() {},
    },
  );
  assert.equal(elapsed, 180000);
  assert.deepEqual(
    results.map((result) => result.ok),
    [true, false, true, true, true],
  );
});

test("manual build metadata is valid without a revision; unsafe inputs never fetch", async () => {
  const results = await run(async (url) =>
    url.endsWith("/build-info.json")
      ? Response.json(metadata(null))
      : healthy(url),
  );
  assert.equal(
    results.every((result) => result.ok),
    true,
  );
  const options = {
    fetchImpl() {
      assert.fail("must validate before fetching");
    },
  };
  await assert.rejects(
    smokeLive("http://site.test", "https://api.test", undefined, options),
    /HTTPS/,
  );
  await assert.rejects(
    smokeLive("https://site.test", "https://api.test", "master", options),
    /commit SHA/,
  );
});
