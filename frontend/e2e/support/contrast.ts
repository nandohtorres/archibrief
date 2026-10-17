// WCAG 2.x contrast check over the rendered page. Runs in the
// browser via page.evaluate, so it measures the colors actually painted
// after theme tokens resolve. Handles HTML text (nearest opaque ancestor
// background) and SVG <text> (fill of the shape drawn under it in the
// same group, else the SVG's own background).
import type { Page } from "@playwright/test";

export interface ContrastFailure {
  text: string;
  ratio: number;
  required: number;
  color: string;
  background: string;
}

export async function findContrastFailures(page: Page): Promise<ContrastFailure[]> {
  return page.evaluate(() => {
    function parse(color: string): number[] | null {
      const m = color.match(/rgba?\(([^)]+)\)/);
      if (!m) return null;
      const parts = m[1]
        .split(/[ ,/]+/)
        .filter(Boolean)
        .map(Number);
      return [parts[0], parts[1], parts[2], parts.length > 3 ? parts[3] : 1];
    }
    function luminance([r, g, b]: number[]): number {
      const c = [r, g, b].map((v) => {
        const s = v / 255;
        return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
    }
    function ratio(a: number[], b: number[]): number {
      const [l1, l2] = [luminance(a), luminance(b)].sort((x, y) => y - x);
      return (l1 + 0.05) / (l2 + 0.05);
    }
    // Composite a translucent color over an opaque base.
    function over(top: number[], base: number[]): number[] {
      const a = top[3];
      return [0, 1, 2].map((i) => top[i] * a + base[i] * (1 - a)).concat(1);
    }
    function backgroundOf(el: Element): number[] {
      const layers: number[][] = [];
      for (let node: Element | null = el; node; node = node.parentElement) {
        const c = parse(getComputedStyle(node).backgroundColor);
        if (c && c[3] > 0) {
          layers.push(c);
          if (c[3] >= 1) break;
        }
      }
      let result = [255, 255, 255, 1];
      for (const layer of layers.reverse()) result = over(layer, result);
      return result;
    }
    function svgBackgroundOf(text: Element): number[] {
      const group = text.closest("g");
      const shape = group?.querySelector("rect, circle, ellipse");
      const fill = shape ? parse(getComputedStyle(shape).fill) : null;
      const svg = text.closest("svg") ?? text;
      const base = backgroundOf(svg);
      return fill && fill[3] > 0 ? over(fill, base) : base;
    }
    function visible(el: Element): boolean {
      // Content of a closed <details> is skipped by the browser's style
      // engine, so its computed colors can be stale. It isn't shown anyway.
      const details = el.closest("details");
      if (details && !details.open && !el.closest("summary")) return false;
      const style = getComputedStyle(el);
      const box = el.getBoundingClientRect();
      return (
        style.visibility !== "hidden" &&
        style.display !== "none" &&
        Number(style.opacity) > 0.1 &&
        box.width > 0 &&
        box.height > 0
      );
    }

    const failures: {
      text: string;
      ratio: number;
      required: number;
      color: string;
      background: string;
    }[] = [];
    const seen = new Set<Element>();
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const el = node.parentElement;
      const content = node.textContent?.trim();
      if (!el || !content || seen.has(el)) continue;
      seen.add(el);
      if (!visible(el) || el.closest("[aria-hidden='true'], .skip-link, option")) continue;
      // WCAG exempts inactive controls.
      if (el.closest("button:disabled, input:disabled, select:disabled")) continue;

      const style = getComputedStyle(el);
      const isSvgText = el instanceof SVGElement;
      const fg = parse(isSvgText ? style.fill : style.color);
      if (!fg) continue;
      const bg = isSvgText ? svgBackgroundOf(el) : backgroundOf(el);
      const painted = fg[3] < 1 ? over(fg, bg) : fg;
      // SVG text inside a scaled diagram renders at its on-screen size.
      const size = isSvgText ? el.getBoundingClientRect().height * 0.8 : parseFloat(style.fontSize);
      const bold = Number(style.fontWeight) >= 700;
      const large = size >= 24 || (bold && size >= 18.66);
      const required = large ? 3 : 4.5;
      const value = ratio(painted, bg);
      if (value < required) {
        failures.push({
          text: content.slice(0, 60),
          ratio: Math.round(value * 100) / 100,
          required,
          color: isSvgText ? style.fill : style.color,
          background: `rgb(${bg.slice(0, 3).map(Math.round).join(", ")})`,
        });
      }
    }
    return failures;
  });
}
