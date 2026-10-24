import { confidenceFromShare, formatDelta, formatNumber, formatPercent } from "./format";

describe("formatDelta", () => {
  it("shows sign and up arrow for gains", () => {
    expect(formatDelta(4.1)).toEqual({ text: "+4.1 ▲", tone: "positive", sign: 1 });
  });
  it("shows sign and down arrow for losses", () => {
    expect(formatDelta(-2)).toEqual({ text: "-2.0 ▼", tone: "negative", sign: -1 });
  });
  it("shows ~ and neutral tone inside the noise band, either sign", () => {
    expect(formatDelta(0.4)).toEqual({ text: "~0.4", tone: "neutral", sign: 0 });
    expect(formatDelta(-0.4).text).toBe("~0.4");
    expect(formatDelta(0).text).toBe("~0.0");
  });
  it("treats the noise threshold itself as a real change", () => {
    expect(formatDelta(0.5).text).toBe("+0.5 ▲");
  });
  it("keeps the sign when a noise-band value rounds up to the threshold", () => {
    expect(formatDelta(0.45)).toEqual({ text: "+0.5", tone: "neutral", sign: 0 });
    expect(formatDelta(-0.45).text).toBe("-0.5");
    expect(formatDelta(0.449).text).toBe("~0.4");
  });
  it("treats negative zero as zero", () => {
    expect(formatDelta(-0.0).text).toBe("~0.0");
  });
  it("rounds to one decimal", () => {
    expect(formatDelta(4.04).text).toBe("+4.0 ▲");
    expect(formatDelta(-1.26).text).toBe("-1.3 ▼");
  });
  it("never prints a negative zero", () => {
    expect(formatNumber(-0.04)).toBe("0.0");
  });
  it("handles non-finite input", () => {
    expect(formatDelta(Number.NaN).text).toBe("–");
  });
});

describe("formatPercent", () => {
  it("rounds to whole percent", () => {
    expect(formatPercent(0.624)).toBe("62%");
    expect(formatPercent(0.625)).toBe("63%");
  });
  it("shows a dash when missing", () => {
    expect(formatPercent(null)).toBe("–");
  });
});

describe("confidenceFromShare", () => {
  it("buckets at 70% and 55%", () => {
    expect(confidenceFromShare(0.7)).toBe("clear");
    expect(confidenceFromShare(0.69)).toBe("lean");
    expect(confidenceFromShare(0.55)).toBe("lean");
    expect(confidenceFromShare(0.54)).toBe("toss-up");
  });
});
