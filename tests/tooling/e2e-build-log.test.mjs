import assert from "node:assert/strict";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { runLoggedCommand } from "../../frontend/e2e/build-log.mjs";
import { writeBuildInfo } from "../../scripts/write_frontend_build_info.mjs";

const outputRoot = path.resolve(
  import.meta.dirname,
  `../../backend/build/tooling-tests-${process.pid}`,
);

test("build metadata fingerprints the actual index and excludes unrelated environment values", () => {
  const frontend = path.join(outputRoot, "frontend");
  mkdirSync(path.join(frontend, "out"), { recursive: true });
  writeFileSync(path.join(frontend, "out", "index.html"), "<html>test</html>");
  const info = writeBuildInfo(
    frontend,
    { GITHUB_SHA: "a".repeat(40), AWS_SECRET_ACCESS_KEY: "PRIVATE-CANARY" },
    new Date("2026-10-24T00:00:00Z"),
  );
  assert.equal(info.source_revision, "a".repeat(40));
  assert.equal(info.backend_revision_verified, false);
  assert.equal(info.index_sha256.length, 64);
  assert.equal(JSON.stringify(info).includes("PRIVATE"), false);
  assert.equal(
    JSON.parse(
      readFileSync(path.join(frontend, "out", "build-info.json"), "utf8"),
    ).index_sha256,
    info.index_sha256,
  );
  assert.equal(
    writeBuildInfo(frontend, { GITHUB_SHA: "not-a-revision" }).source_revision,
    null,
  );
});

test("build metadata refuses output outside the frontend directory", () => {
  const frontend = path.join(outputRoot, "scope-check");
  mkdirSync(frontend, { recursive: true });
  assert.throws(
    () => writeBuildInfo(frontend, { NEXT_DIST_DIR: ".." }),
    /must stay inside/,
  );
});

test("success captures both streams in the diagnostic file", () => {
  const logFile = path.join(outputRoot, "success.log");
  runLoggedCommand({
    command: process.execPath,
    args: [
      "-e",
      "process.stdout.write('BUILD-OUT');process.stderr.write('BUILD-ERR')",
    ],
    logFile,
    echo: false,
  });
  const log = readFileSync(logFile, "utf8");
  assert.match(log, /Build started:/);
  assert.match(log, /BUILD-OUT/);
  assert.match(log, /BUILD-ERR/);
});

test("a failed build still leaves stdout and stderr before reporting failure", () => {
  const logFile = path.join(outputRoot, "failure.log");
  assert.throws(
    () =>
      runLoggedCommand({
        command: process.execPath,
        args: [
          "-e",
          "process.stdout.write('PARTIAL-OUT');process.stderr.write('BUILD-FAILED');process.exit(7)",
        ],
        logFile,
        echo: false,
      }),
    (error) => error.buildStatus === 7,
  );
  const log = readFileSync(logFile, "utf8");
  assert.match(log, /PARTIAL-OUT/);
  assert.match(log, /BUILD-FAILED/);
});
