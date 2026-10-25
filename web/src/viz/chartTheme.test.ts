import { readFileSync } from "node:fs";
import { TICK_COLOR, axisCaption } from "./chartTheme";

const css = readFileSync(`${__dirname}/../index.css`, "utf8");

function token(block: string, name: string): string {
  const m = new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6})`).exec(block);
  if (!m?.[1]) throw new Error(`missing ${name}`);
  return m[1];
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

describe("chart theme", () => {
  it("tick colour is the muted text token and meets 4.5:1 on the dark page and surface", () => {
    expect(TICK_COLOR).toBe("var(--text-muted)");
    const dark = css.slice(css.indexOf(":root,\n.theme-dark"), css.indexOf("/* Small screens"));
    const muted = token(dark, "--text-muted");
    expect(contrast(muted, token(dark, "--page"))).toBeGreaterThanOrEqual(4.5);
    expect(contrast(muted, token(dark, "--surface"))).toBeGreaterThanOrEqual(4.5);
  });

  it("axis caption carries its text in the muted tick colour", () => {
    expect(axisCaption("Chance (%)")).toMatchObject({ value: "Chance (%)", style: { fill: TICK_COLOR } });
  });
});
