import { readFileSync } from "node:fs";
import { join } from "node:path";

// A Google Fonts @import with "&amp;" between families (HTML escaping,
// wrong in CSS) loads only the first family, and the site silently falls
// back to system fonts. Fonts come from next/font in layout.tsx; these
// checks keep it that way.
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
