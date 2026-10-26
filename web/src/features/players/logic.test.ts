import { describe, expect, it } from "vitest";
import type { OutlookRow } from "@/features/outlook/types";
import { ALL_POSITIONS, filterByPosition, isOut, positionsIn, sortByChange } from "./logic";

const row = (position: string, change: number | null, chance: number | null = 1) =>
  ({ gsis_id: `${position}${change}`, full_name: "x", position, owner: "o", recent_ppg: 1, expected_ppg: 1, next_ppg: 1, change, chance_to_play: chance, label: "Steady", why: "" }) as OutlookRow;

describe("players logic", () => {
  const rows = [row("WR", 1), row("QB", null), row("RB", 3), row("K", -2)];
  it("sorts biggest gain first, missing last, without mutating", () => {
    expect(sortByChange(rows).map((r) => r.change)).toEqual([3, 1, -2, null]);
    expect(rows[0]?.change).toBe(1);
  });
  it("lists present positions in the usual order after All", () => {
    expect(positionsIn(rows)).toEqual([ALL_POSITIONS, "QB", "RB", "WR", "K"]);
  });
  it("filters by position", () => {
    expect(filterByPosition(rows, "RB")).toHaveLength(1);
    expect(filterByPosition(rows, ALL_POSITIONS)).toHaveLength(4);
  });
  it("flags a 0% chance to play only", () => {
    expect(isOut(row("WR", 1, 0))).toBe(true);
    expect(isOut(row("WR", 1, 0.4))).toBe(false);
    expect(isOut(row("WR", 1, null))).toBe(false);
  });
});
