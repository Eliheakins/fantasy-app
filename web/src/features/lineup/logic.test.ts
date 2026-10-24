import { describe, expect, test } from "vitest";
import { type ComparisonRow, type LineupRow, collapseComparison, collapsedNote, headline, injuryLabel, rowsFor, splitLineup } from "./logic";

const cmp = (option: string, win: number): ComparisonRow => ({ option, win_prob: win, expected_points: 100, floor: 80, median: 100, ceiling: 120 });
const row = (id: string, o: Partial<LineupRow> = {}): LineupRow => ({
  slot: "RB", gsis_id: id, full_name: id, position: "RB", projection: 10, p10: 4, p90: 18,
  starting_now: false, recommended: true, injury: null, injury_note: null, locked: false, actual: 0, game: "", change: "", ...o,
});

describe("lineup logic", () => {
  test("collapses identical comparison rows into one with a note", () => {
    const groups = collapseComparison([cmp("Expected points", 0.5), cmp("Win probability", 0.5), cmp("Max floor", 0.4)]);
    expect(groups.map((g) => g.labels)).toEqual([["Expected points", "Win probability"], ["Max floor"]]);
    expect(collapsedNote(groups)).toBe("Expected points and Win probability pick the same lineup, so they share one row.");
  });
  test("no note when all rows differ", () => {
    expect(collapsedNote(collapseComparison([cmp("a", 0.5), cmp("b", 0.6)]))).toBeNull();
  });
  test("headline computes from rows without a summary", () => {
    const rows = [row("a", { projection: 10, starting_now: true }), row("b", { projection: 12, starting_now: false })];
    expect(headline(rows, undefined)).toEqual({ shown: 22, now: 10, gap: -12, win: null });
    expect(headline([row("a")], undefined).now).toBeNull();
  });
  test("rowsFor falls back to base rows", () => {
    const base = [row("a")];
    expect(rowsFor(base, null, "max_floor")).toBe(base);
  });
  test("splitLineup and injuryLabel", () => {
    const { start, bench } = splitLineup([row("a"), row("b", { recommended: false })]);
    expect([start.length, bench.length]).toEqual([1, 1]);
    expect(injuryLabel({ injury: "Q", injury_note: null })).toBe("Q");
    expect(injuryLabel({ injury: null, injury_note: null })).toBeNull();
  });
});
