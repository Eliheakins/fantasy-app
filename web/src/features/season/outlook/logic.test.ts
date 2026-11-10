import { canShowHistory, dodgeLabels, rankOdds, historyTeams, weeklyHistory, seedFill } from "./logic";
import type { OddsHistoryRow, SeasonOddsRow } from "@/lib/outlookTypes";

const odds: SeasonOddsRow[] = [
  { roster_id: 1, team_name: "Me", p_playoffs: 0.7, p_bye: 0.2, p_title: 0.1, exp_wins: 8, is_me: true },
  { roster_id: 2, team_name: "Them", p_playoffs: 0.4, p_bye: 0.1, p_title: 0.05, exp_wins: 7, is_me: false },
];
const h = (run_at: string, roster_id: number, p: number, as_of_week: number | null = run_at === "a" ? 7 : 8): OddsHistoryRow => ({
  run_at,
  roster_id,
  team_name: roster_id === 1 ? "Me" : "Them",
  p_playoffs: p,
  p_title: p / 2,
  as_of_week,
});

it("ranks by playoff odds without mutating", () => {
  const rows = [odds[1]!, odds[0]!];
  expect(rankOdds(rows).map((r) => r.roster_id)).toEqual([1, 2]);
  expect(rows[0]!.roster_id).toBe(2);
});

describe("odds history logic", () => {
  it("needs two distinct weeks", () => {
    const one = [h("a", 1, 0.5), h("a", 2, 0.4)];
    expect(canShowHistory(odds, one)).toBe(false);
    expect(canShowHistory(odds, [...one, h("a2", 1, 0.6, 7)])).toBe(false);
    expect(canShowHistory(odds, [...one, h("b", 1, 0.6)])).toBe(true);
  });
  it("keeps the last snapshot of each week, by week, and skips runs without a week", () => {
    const rows = [
      h("2026-10-21", 1, 0.5, 7),
      h("2026-10-24", 1, 0.55, 7),
      h("2026-10-24", 2, 0.3, 7),
      h("2026-10-28", 1, 0.7, 8),
      h("2026-10-01", 1, 0.9, null),
    ];
    expect(weeklyHistory(rows)).toEqual([
      { week: 7, run_at: "2026-10-24", "1": 0.55, "2": 0.3 },
      { week: 8, run_at: "2026-10-28", "1": 0.7 },
    ]);
  });
  it("colours playoff seeds Forest, the rest light grey", () => {
    expect([1, 2, 6, 7, 10].map((s) => seedFill(s))).toEqual([
      "var(--lf-forest)",
      "var(--lf-forest)",
      "var(--lf-forest)",
      "var(--lf-chart-other)",
      "var(--lf-chart-other)",
    ]);
  });
  it("needs my team", () => {
    const rivals = odds.map((o) => ({ ...o, is_me: false }));
    expect(canShowHistory(rivals, [h("a", 1, 1), h("b", 1, 1)])).toBe(false);
  });
  it("names teams and flags mine", () => {
    expect(historyTeams(odds, [h("a", 1, 1), h("a", 2, 1)])).toEqual([
      { id: "1", name: "Me", isMe: true },
      { id: "2", name: "Them", isMe: false },
    ]);
  });
});

describe("dodgeLabels", () => {
  it("leaves well-spaced labels where they are, in input order", () => {
    expect(dodgeLabels([100, 20, 60], 12, 0, 200)).toEqual([100, 20, 60]);
  });
  it("pushes bunched labels apart by the minimum gap", () => {
    const out = dodgeLabels([50, 52, 51], 12, 0, 200);
    const [a, b, c] = [...out].sort((x, y) => x - y);
    expect(b! - a!).toBeGreaterThanOrEqual(12);
    expect(c! - b!).toBeGreaterThanOrEqual(12);
    expect(out[0]!).toBeLessThan(out[2]!);
    expect(out[2]!).toBeLessThan(out[1]!);
  });
  it("clamps to the plot area, pushing a stack at the bottom up", () => {
    expect(dodgeLabels([199, 200, 198], 12, 0, 200)).toEqual([188, 200, 176]);
    expect(dodgeLabels([0, 1], 12, 0, 200)).toEqual([0, 12]);
  });
  it("handles empty input and a plot too small for the gap", () => {
    expect(dodgeLabels([], 12, 0, 200)).toEqual([]);
    expect(dodgeLabels([5, 6, 7], 12, 0, 10).every((y) => y >= 0 && y <= 10)).toBe(true);
  });
});
