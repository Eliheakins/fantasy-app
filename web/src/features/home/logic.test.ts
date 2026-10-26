import type { League } from "@/api/types";
import { actionPoints, actionShare, myOdds, myRange, opponentRange, recordLine, oddsPercent, actionSentence, worthActing, splitRoster, winChance, type WinProbability } from "./logic";

const league = {
  wins: 4, losses: 2, ties: 0, record: "4-2", points_for: 854.72, current_week: 7,
} as League;
const option = (o: string, win_prob: number, share_better = 0.5) =>
  ({ option: o, win_prob, share_better, floor: 90, median: 110, ceiling: 130, opp_floor: 80, opp_median: 100, opp_ceiling: 120 }) as WinProbability["options"][number];
const wp = { options: [option("max_points", 0.62), option("win_prob", 0.7, 0.8)] } as WinProbability;

describe("home logic", () => {
  it("builds the record line with Streamlit's fallbacks", () => {
    expect(recordLine(league)).toBe("4-2 · 854.7 PF · week 7");
    expect(recordLine({ ...league, wins: null, points_for: null, current_week: null })).toBe(
      "no record yet · no PF · week unknown",
    );
  });
  it("shows odds as whole percents, one decimal under 10%", () => {
    expect(oddsPercent(0.1234)).toBe("12%");
    expect(oddsPercent(0.079)).toBe("7.9%");
    expect(oddsPercent(null)).toBe("–");
  });
  it("strips the confidence word and the point gain from an action sentence", () => {
    expect(actionSentence("Lean: start A over B (98.6% vs 98.3% to win)")).toBe("start A over B (98.6% vs 98.3% to win)");
    expect(actionSentence("Add X, drop Y: +0.7% playoff odds, +2.9 points")).toBe("Add X, drop Y: +0.7% playoff odds");
  });
  it("keeps only actions outside the noise band", () => {
    const win = (t: string) => ({ kind: "Win probability", text: t });
    expect(worthActing(win("Clear: a (98.6% vs 98.3% to win)"), 0.8)).toBe(false);
    expect(worthActing(win("Clear: a (62.0% vs 60.0% to win)"), 0.8)).toBe(true);
    expect(worthActing(win("Lean: a (62.0% vs 60.0% to win)"), 0.5)).toBe(false);
    expect(worthActing({ kind: "Waiver", text: "Add X: +0.2 points", delta_points: 0.2 }, null)).toBe(false);
    expect(worthActing({ kind: "Waiver", text: "Add X: +2.9 points", delta_points: 2.9 }, null)).toBe(true);
  });
  it("splits starters from bench", () => {
    const r = [{ is_starter: true }, { is_starter: false }] as never;
    expect(splitRoster(r).bench).toHaveLength(1);
  });
  it("picks my row and the max-points option", () => {
    expect(myOdds([{ is_me: false }, { is_me: true, team_name: "x" }] as never)?.team_name).toBe("x");
    expect(winChance(wp)).toBe(0.62);
    expect(myRange(wp)).toEqual({ p10: 90, p50: 110, p90: 130 });
    expect(opponentRange(wp)).toEqual({ p10: 80, p50: 100, p90: 120 });
    expect(opponentRange({ options: [] } as never)).toBeNull();
    expect(winChance({ options: [] } as never)).toBeNull();
  });
  it("reads the gain out of action text", () => {
    expect(actionPoints("Start A over B (+4.1 points)")).toBe(4.1);
    expect(actionPoints("Add X: +1.0% playoff odds, -0.3 points")).toBe(-0.3);
    expect(actionPoints("Chase is Out and in your lineup")).toBeNull();
  });
  it("gives confidence only to the win-probability action", () => {
    expect(actionShare({ kind: "Win probability", text: "" }, wp)).toBe(0.8);
    expect(actionShare({ kind: "Lineup", text: "" }, wp)).toBeNull();
  });
});
