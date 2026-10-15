import { readFileSync } from "node:fs";
import { join } from "node:path";

// Until 2026-10-15 a Google Fonts @import in globals.css used "&amp;"
// between families (HTML escaping, wrong in CSS), so only the first family
// loaded and the site fell back to system fonts unnoticed. Fonts now come
// from next/font in layout.tsx; these checks keep it that way.
const frontend = join(__dirname, "../../../frontend/app");
const css = readFileSync(join(frontend, "globals.css"), "utf8");
const layout = readFileSync(join(frontend, "layout.tsx"), "utf8");

describe("site fonts", () => {
  it("loads all three families through next/font", () => {
    expect(layout).toMatch(
      /import \{ IBM_Plex_Mono, IBM_Plex_Sans, Source_Serif_4 \} from "next\/font\/google"/,
    );
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
});
