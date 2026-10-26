import {
  barSpan, formatAge, ideasNotice, maxAbsDiff, nextLineupAction, oddsComparison, resultSentence, toPoints,
} from "./logic";
import type { ActionRow, IdeasInfo, LastWeekRow, OddsChangeRow, ProjectionMissRow } from "./types";

const NOW = Date.parse("2026-10-25T12:00:00Z");
const ideas = (over: Partial<IdeasInfo> = {}): IdeasInfo => ({
  is_mine: true, created_at: "2026-10-25T08:00:00+00:00", as_of_week: 7, current_week: 7, trade_deadline: 11, deadline_passed: false, ...over,
});

describe("formatAge", () => {
  it.each([
    ["2026-10-25T11:59:40Z", "just now"],
    ["2026-10-25T11:30:00Z", "30 minutes ago"],
    ["2026-10-25T08:00:00Z", "4 hours ago"],
    ["2026-10-24T11:00:00Z", "1 day ago"],
    ["2026-10-20T12:00:00Z", "5 days ago"],
    ["2026-10-25T13:00:00Z", "just now"],
    ["not a date", "unknown age"],
  ])("%s is %s", (iso, text) => {
    expect(formatAge(iso, NOW)).toBe(text);
  });
});

describe("toPoints", () => {
  it("turns a fraction into percentage points and keeps null null", () => {
    expect(toPoints(0.05)).toBeCloseTo(5);
    expect(toPoints(null)).toBeNull();
    expect(toPoints(0)).toBe(0);
  });
});

describe("bar of the projection miss", () => {
  const rows = [{ diff: 10 }, { diff: -4 }, { diff: null }] as ProjectionMissRow[];
  it("scales to the biggest miss, ignoring nulls", () => {
    expect(maxAbsDiff(rows)).toBe(10);
    expect(maxAbsDiff([{ diff: null }] as ProjectionMissRow[])).toBe(0);
  });
  it("puts a gain right of the centre line and a shortfall left of it", () => {
    expect(barSpan(10, 10, 50)).toEqual({ x: 50, width: 50 });
    expect(barSpan(-5, 10, 50)).toEqual({ x: 25, width: 25 });
    expect(barSpan(null, 10, 50)).toBeNull();
    expect(barSpan(3, 0, 50)).toBeNull();
  });
});

describe("resultSentence", () => {
  const row = { week: 6, result: "W", points: 137.82, opp_points: 76.38, opponent: "Eggplant" } as LastWeekRow;
  it("names the result, the scores and the opponent", () => {
    expect(resultSentence(row)).toBe("Won 137.8 to 76.4 against Eggplant");
    expect(resultSentence({ ...row, result: "L", points: 80, opp_points: 90 })).toBe("Lost 80.0 to 90.0 against Eggplant");
    expect(resultSentence({ ...row, result: "T", points: 80, opp_points: 80 })).toBe("Tied 80.0 to 80.0 against Eggplant");
  });
});

describe("oddsComparison", () => {
  const base = { roster_id: 1, team_name: "A", is_me: true, as_of_week: 7, p_playoffs: 0.8, p_title: 0.2 };
  it("says no earlier run when nothing is to compare, never zero", () => {
    const rows = [{ ...base, prev_as_of_week: null, d_playoffs: null, d_title: null }] as OddsChangeRow[];
    expect(oddsComparison(rows)).toEqual({ latest: 7, previous: null });
  });
  it("names both weeks", () => {
    const rows = [{ ...base, as_of_week: 8, prev_as_of_week: 7, d_playoffs: 0.01, d_title: 0 }] as OddsChangeRow[];
    expect(oddsComparison(rows)).toEqual({ latest: 8, previous: 7 });
    expect(oddsComparison([])).toBeNull();
  });
});

describe("ideasNotice", () => {
  it("is empty when ideas are fresh", () => {
    expect(ideasNotice(ideas(), "trade")).toBeNull();
  });
  it("says ideas exist for the owner's team only when another team is viewed", () => {
    expect(ideasNotice(ideas({ is_mine: false }), "waiver")).toMatch(/only for the team that is yours/);
  });
  it("says the digest has not run when nothing is stored", () => {
    expect(ideasNotice(ideas({ created_at: null, as_of_week: null }), "waiver")).toMatch(/make refresh/);
  });
  it("says the deadline passed for trades only", () => {
    const passed = ideas({ deadline_passed: true, trade_deadline: 11, current_week: 12, as_of_week: 12 });
    expect(ideasNotice(passed, "trade")).toMatch(/deadline \(week 11\) has passed/);
    expect(ideasNotice(passed, "waiver")).toBeNull();
  });
  it("warns when the ideas are from an earlier week", () => {
    expect(ideasNotice(ideas({ current_week: 8 }), "waiver")).toMatch(/from week 7.*week 8/);
  });
});

describe("nextLineupAction", () => {
  const a = (kind: string, text = kind): ActionRow => ({ kind, text, delta_points: null, share_better: null });
  it("skips waiver actions and returns the first lineup one", () => {
    expect(nextLineupAction([a("Waiver"), a("Lineup", "Start A over B (+3.0 points)")])?.kind).toBe("Lineup");
  });
  it("is null when there is none", () => {
    expect(nextLineupAction([a("Waiver")])).toBeNull();
    expect(nextLineupAction([])).toBeNull();
  });
});
