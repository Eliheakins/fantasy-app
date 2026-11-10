import { describe, expect, it } from "vitest";
import { barShare, rankedStrength } from "./logic";

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
