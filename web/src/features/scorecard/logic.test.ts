import { describe, expect, test } from "vitest";
import { leftOutText, positionLines, weekLines, weeksText, type ScorecardRow } from "./logic";

const r = (o: Partial<ScorecardRow>): ScorecardRow => ({
  week: 7, position: "ALL", tier: -1, model: "learned", n: 100, mae: 5, rmse: 6, bias: 0, ...o,
});

describe("scorecard lines", () => {
  test("marks the lowest MAE per row as best and needs two models", () => {
    const rows = [r({ model: "learned", mae: 5.2 }), r({ model: "baseline", mae: 5.0 })];
    expect(weekLines(rows)[0]?.best).toBe("baseline");
    expect(weekLines([r({})])[0]?.best).toBeNull();
  });
  test("week lines are in numeric order and skip the all-weeks rows", () => {
    const rows = [r({ week: 10 }), r({ week: 9 }), r({ week: null })];
    expect(weekLines(rows).map((l) => l.label)).toEqual(["Week 9", "Week 10"]);
  });
  test("position lines put All first and flag a small sample", () => {
    const rows = [r({ week: null, position: "WR", n: 12 }), r({ week: null, position: "ALL" })];
    const lines = positionLines(rows);
    expect(lines.map((l) => l.label)).toEqual(["All positions", "WR"]);
    expect(lines.map((l) => l.small)).toEqual([false, true]);
  });
  test("texts", () => {
    expect(weeksText([])).toBe("none");
    expect(weeksText([7])).toBe("week 7");
    expect(leftOutText({ games: 5, scored: 1, not_final: 3, no_kickoff: 0, no_snapshot: 1, sleeper_missing: 0 })).toBe(
      "Left out: 3 not final yet; 1 no snapshot fetched before kickoff.",
    );
  });
});
