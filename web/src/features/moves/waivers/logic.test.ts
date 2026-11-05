import { describe, expect, it } from "vitest";
import { barShare, classifyChange, rankedStrength } from "./logic";

describe("classifyChange", () => {
  it("is noise inside the Monte Carlo error", () => {
    expect(classifyChange(0.004, 0.005)).toMatchObject({ kind: "noise", noiseText: "~0.4" });
    expect(classifyChange(-0.03, 0.03).kind).toBe("noise");
  });
  it("is a delta in percentage points outside the error", () => {
    const c = classifyChange(0.041, 0.005);
    expect(c.kind).toBe("delta");
    expect(c.points).toBeCloseTo(4.1);
  });
  it("is missing for null", () => expect(classifyChange(null).kind).toBe("missing"));
  it("with no error, never noise", () => expect(classifyChange(0.001).kind).toBe("delta"));
});

describe("strength", () => {
  const rows = [
    { position: "WR", vor_per_week: 2, rank: 3, teams: 12 },
    { position: "QB", vor_per_week: 8, rank: 1, teams: 12 },
  ];
  it("sorts by rank", () => expect(rankedStrength(rows).map((r) => r.position)).toEqual(["QB", "WR"]));
  it("scales bars to the largest", () => {
    expect(barShare(2, rows)).toBe(0.25);
    expect(barShare(1, [])).toBe(0);
  });
});
