import { readFileSync } from "node:fs";
import { join } from "node:path";

// The Google Fonts import once used "&amp;" between families (HTML escaping,
// wrong in CSS), so only the first family loaded and the site fell back to
// system fonts unnoticed (found 2026-10-15).
describe("font import", () => {
  const css = readFileSync(
    join(__dirname, "../../../frontend/app/globals.css"),
    "utf8",
  );
  const importUrl = css.match(/@import url\("([^"]+)"\)/)?.[1] ?? "";

  it("is a valid query string", () => {
    expect(importUrl).not.toBe("");
    expect(importUrl).not.toContain("&amp;");
  });

  it("requests every family the styles use", () => {
    const families = new URL(importUrl).searchParams
      .getAll("family")
      .map((f) => f.split(":")[0]);
    expect(families).toEqual([
      "IBM Plex Mono",
      "IBM Plex Sans",
      "Source Serif 4",
    ]);
  });
});
