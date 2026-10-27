import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { join } from "node:path";

// A Google Fonts @import with "&amp;" between families (HTML escaping,
// wrong in CSS) loads only the first family, and the site silently falls
// back to system fonts. Fonts come from next/font in layout.tsx; these
// checks keep it that way.
const frontend = join(__dirname, "../../../frontend/app");
const css = readFileSync(join(frontend, "globals.css"), "utf8");
const layout = readFileSync(join(frontend, "layout.tsx"), "utf8");

describe("site fonts", () => {
  it("loads all three families locally without a Google build dependency", () => {
    expect(layout).toContain('import localFont from "next/font/local"');
    expect(layout).not.toContain("next/font/google");
    for (const variable of [
      "--font-plex-sans",
      "--font-plex-mono",
      "--font-source-serif",
    ]) {
      expect(layout).toContain(`variable: "${variable}"`);
      expect(css).toContain(`var(${variable})`);
    }
  });

  it("has no external font import left in the CSS", () => {
    expect(css).not.toMatch(/@import\s+url\(/);
  });

  it("ships the unchanged upstream WOFF2 assets and licenses", () => {
    const manifest = JSON.parse(
      readFileSync(join(frontend, "fonts/manifest.json"), "utf8"),
    );
    for (const entry of manifest) {
      const bytes = readFileSync(join(frontend, "fonts", entry.file));
      expect(bytes.subarray(0, 4).toString()).toBe("wOF2");
      expect(createHash("sha256").update(bytes).digest("hex")).toBe(
        entry.sha256,
      );
      expect(layout).toContain(`./fonts/${entry.file}`);
    }
    for (const family of ["ibm-plex-sans", "ibm-plex-mono", "source-serif"]) {
      expect(
        readFileSync(join(frontend, "fonts", `${family}-OFL.txt`), "utf8"),
      ).toMatch(/SIL OPEN FONT LICENSE/i);
    }
  });
});
