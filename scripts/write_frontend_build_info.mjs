import { createHash } from "node:crypto";
import { readFileSync, realpathSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export function writeBuildInfo(
  frontendDir,
  environment = process.env,
  now = new Date(),
) {
  const frontend = realpathSync(frontendDir);
  const output = realpathSync(
    path.resolve(frontend, environment.NEXT_DIST_DIR || "out"),
  );
  const relative = path.relative(frontend, output);
  if (
    !relative ||
    relative === ".." ||
    relative.startsWith(`..${path.sep}`) ||
    path.isAbsolute(relative)
  ) {
    throw new Error("Build output must stay inside the frontend directory");
  }
  const candidate =
    environment.ARCHIBRIEF_BUILD_REVISION || environment.GITHUB_SHA;
  const revision =
    typeof candidate === "string" && /^[a-f0-9]{40}$/.test(candidate)
      ? candidate
      : null;
  const info = {
    schema_version: "frontend-build@1",
    source_revision: revision,
    revision_source: revision
      ? environment.ARCHIBRIEF_BUILD_REVISION
        ? "operator-supplied"
        : "github-actions"
      : "unrecorded",
    built_at: now.toISOString(),
    index_sha256: createHash("sha256")
      .update(readFileSync(path.join(output, "index.html")))
      .digest("hex"),
    backend_revision_verified: false,
  };
  writeFileSync(
    path.join(output, "build-info.json"),
    JSON.stringify(info, null, 2) + "\n",
    "utf8",
  );
  return info;
}

if (
  process.argv[1] &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  writeBuildInfo(fileURLToPath(new URL("../frontend/", import.meta.url)));
}
