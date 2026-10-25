import { describe, expect, it } from "vitest";
import { MIN_RUNS, barFraction, formatRecord, groupMatchups, isThin, scheduleOrder } from "./logic";
import type { PowerRankingRow, WhatIfRow } from "./types";

const outcome = (winner_id: number, loser_id: number, o: Partial<WhatIfRow> = {}): WhatIfRow => ({
  winner_id, loser_id, winner: `T${winner_id}`, loser: `T${loser_id}`, involves_me: false,
  p_condition: 0.5, n_runs: 10000, d_playoffs: 0, d_title: 0, ...o,
});

describe("groupMatchups", () => {
  it("pairs the two outcomes of a matchup in backend order and flags mine", () => {
    const rows = [
      outcome(1, 4, { involves_me: true }), outcome(4, 1, { involves_me: true }),
      outcome(2, 3), outcome(3, 2),
    ];
    const groups = groupMatchups(rows);
    expect(groups.map((g) => g.label)).toEqual(["T1 vs T4", "T2 vs T3"]);
    expect(groups[0]?.involvesMe).toBe(true);
    expect(groups[0]?.outcomes).toHaveLength(2);
    expect(groups[1]?.involvesMe).toBe(false);
  });
  it("keeps a lone outcome and returns nothing for no rows", () => {
    expect(groupMatchups([outcome(1, 2)])[0]?.outcomes).toHaveLength(1);
    expect(groupMatchups([])).toEqual([]);
  });
});

describe("isThin", () => {
  it("hides outcomes under the run floor, keeps the floor itself", () => {
    expect(isThin(outcome(1, 2, { n_runs: MIN_RUNS - 1 }))).toBe(true);
    expect(isThin(outcome(1, 2, { n_runs: MIN_RUNS }))).toBe(false);
  });
});

describe("barFraction", () => {
  it("scales to the largest value and survives zero, null and negatives", () => {
    expect(barFraction(50, 100)).toBe(0.5);
    expect(barFraction(5, 0)).toBe(0);
    expect(barFraction(null, 100)).toBe(0);
    expect(barFraction(-3, 100)).toBe(0);
  });
});

describe("formatRecord", () => {
  it("drops ties when there are none", () => {
    expect(formatRecord(4, 2, 0)).toBe("4-2");
    expect(formatRecord(4, 2, 1)).toBe("4-2-1");
  });
});

describe("scheduleOrder", () => {
  it("lists the toughest remaining schedule first and unranked teams last", () => {
    const row = (roster_id: number, sos_rank: number | null) => ({ roster_id, sos_rank }) as PowerRankingRow;
    expect(scheduleOrder([row(1, 3), row(2, null), row(3, 1)]).map((r) => r.roster_id)).toEqual([3, 1, 2]);
  });
});
