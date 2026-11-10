import { describe, expect, it } from "vitest";

import { bestIndexes, compareVerdict } from "./compare";
import type { PlayerProfile } from "./profile";

const profile = (median: number | null, ros: number | null) => ({ median, ros_points: ros }) as PlayerProfile;

describe("bestIndexes", () => {
  it("marks the highest value, and every tie for it", () => {
    expect(bestIndexes([3, 9, 9])).toEqual(new Set([1, 2]));
  });

  it("marks nothing when fewer than two players have a value or all are equal", () => {
    expect(bestIndexes([3, null])).toEqual(new Set());
    expect(bestIndexes([4, 4])).toEqual(new Set());
  });
});

describe("compareVerdict", () => {
  it("states both margins for one leader", () => {
    expect(compareVerdict(["Collins", "Moore"], [profile(14.2, 120), profile(12, 102.2)])).toBe(
      "Collins projects +2.2 next game and +17.8 rest of season over Moore.",
    );
  });

  it("splits the sentence when the leaders differ", () => {
    expect(compareVerdict(["A", "B"], [profile(10, 80), profile(12, 90)])).toBe(
      "B projects +2.0 next game and +10.0 rest of season over A.",
    );
    expect(compareVerdict(["A", "B"], [profile(14, 80), profile(12, 90)])).toBe(
      "A projects +2.0 next game over B; B projects +10.0 rest of season over A.",
    );
  });

  it("is null without two projections", () => {
    expect(compareVerdict(["A", "B"], [profile(14, null), profile(null, null)])).toBeNull();
  });
});
