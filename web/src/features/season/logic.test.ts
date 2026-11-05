import type { WhatIfRow } from "@/features/season/league/types";
import { weekMarks, myOddsByWeek, needSentence, needTable, rootFor } from "./logic";
import type { SeasonEventRow, WinNeedRow } from "./types";

const need = (wins: number, p: number, runs = 5000, games = 4): WinNeedRow => ({
  n_games: games, wins, n_runs: runs, p_condition: runs / 20000, p_playoffs: p,
});

describe("needTable", () => {
  it("lists 0 to n_games wins and leaves a gap where no simulated season had that many", () => {
    const table = needTable([need(1, 0.4), need(0, 0.1), need(3, 0.9)]);
    expect(table.map((r) => r.wins)).toEqual([0, 1, 2, 3, 4]);
    expect(table.map((r) => r.row?.p_playoffs ?? null)).toEqual([0.1, 0.4, null, 0.9, null]);
  });
  it("is empty with no rows", () => expect(needTable([])).toEqual([]));
  it("follows fewer games late in the season", () => {
    expect(needTable([need(0, 0.2, 5000, 2), need(2, 0.9, 5000, 2)]).map((r) => r.wins)).toEqual([0, 1, 2]);
  });
});

describe("needSentence", () => {
  it("names the fewest wins that reach 75%", () => {
    expect(needSentence([need(0, 0.1), need(1, 0.5), need(2, 0.8), need(3, 0.95)])).toBe(
      "Win 2 of your next 4 and you are at 80% to make the playoffs.",
    );
  });
  it("says so when even every win is not enough", () => {
    expect(needSentence([need(0, 0.1), need(1, 0.3), need(2, 0.5)])).toBe(
      "Even winning 2 of your next 4 leaves you at 50% to make the playoffs.",
    );
  });
  it("is null with no rows", () => expect(needSentence([])).toBeNull());
  it("ignores win counts seen in fewer than 1,000 runs, keeping exactly 1,000", () => {
    expect(needSentence([need(1, 0.3), need(2, 0.99, 999)])).toContain("Even winning 1 of your next 4 leaves you at 30%");
    expect(needSentence([need(1, 0.3), need(2, 0.99, 1000)])).toContain("Win 2 of your next 4");
    expect(needSentence([need(2, 0.99, 999)])).toBeNull();
  });
});

const outcome = (winner: number, loser: number, d: number, runs = 8000, me = false): WhatIfRow => ({
  winner_id: winner, loser_id: loser, winner: `T${winner}`, loser: `T${loser}`, involves_me: me,
  p_condition: 0.5, n_runs: runs, d_playoffs: d, d_title: 0,
});

describe("rootFor", () => {
  const rows = [
    outcome(1, 9, 0.2, 8000, true), outcome(9, 1, -0.2, 8000, true),
    outcome(2, 3, 0.01), outcome(3, 2, -0.01),
    outcome(4, 5, -0.08), outcome(5, 4, 0.06),
    outcome(6, 7, 0.5, 100), outcome(7, 6, -0.5, 100),
  ];
  it("ranks other matchups by the swing between outcomes and names the side to back", () => {
    const out = rootFor(rows);
    expect(out.map((r) => r.root)).toEqual(["T5", "T2"]);
    expect(out[0]).toMatchObject({ against: "T4", gain: 0.06, swing: 0.14, runs: 8000 });
  });
  it("skips my own game and matchups whose outcomes are too rare to trust", () => {
    const out = rootFor(rows);
    expect(out.some((r) => ["T1", "T9", "T6", "T7"].includes(r.root))).toBe(false);
  });
  it("needs both outcomes to be usable, and 1,000 runs is usable while 999 is not", () => {
    expect(rootFor([outcome(2, 3, 0.2), outcome(3, 2, -0.2, 999)])).toEqual([]);
    expect(rootFor([outcome(2, 3, 0.2, 1000), outcome(3, 2, -0.2, 1000)])).toHaveLength(1);
  });
  it("keeps at most five", () => {
    const many = Array.from({ length: 8 }, (_, i) => [outcome(20 + 2 * i, 21 + 2 * i, 0.01 * (i + 1)), outcome(21 + 2 * i, 20 + 2 * i, -0.01 * (i + 1))]).flat();
    expect(rootFor(many)).toHaveLength(5);
  });
});

describe("weekMarks", () => {
  const ev = (kind: SeasonEventRow["kind"], run_at: string | null): SeasonEventRow => ({ kind, when: "2026-10-25T00:00:00+00:00", run_at, label: `${kind} label` });
  it("groups events by the week of their run and leaves out those with no run", () => {
    const marks = weekMarks([ev("trade", "r1"), ev("injury", "r1"), ev("big_week", "r2"), ev("trade", null)], new Map([["r1", 7], ["r2", 8]]));
    expect(marks.get(7)).toEqual([{ short: "Trade", full: "trade label" }, { short: "Injury", full: "injury label" }]);
    expect(marks.get(8)).toEqual([{ short: "Big week", full: "big_week label" }]);
    expect([...marks.keys()]).toEqual([7, 8]);
  });
});

describe("myOddsByWeek", () => {
  it("keeps my odds at each week's last run", () => {
    const h = [
      { run_at: "r1", roster_id: 1, team_name: "A", p_playoffs: 0.5, p_title: 0, as_of_week: 7 },
      { run_at: "r2", roster_id: 1, team_name: "A", p_playoffs: 0.6, p_title: 0, as_of_week: 7 },
      { run_at: "r2", roster_id: 2, team_name: "B", p_playoffs: 0.9, p_title: 0, as_of_week: 7 },
    ];
    expect([...myOddsByWeek(h, 1)]).toEqual([[7, 0.6]]);
    expect(myOddsByWeek(h, undefined).size).toBe(0);
  });
});
