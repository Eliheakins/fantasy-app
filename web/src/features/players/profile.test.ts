import { describe, expect, it } from "vitest";
import {
  answerSentence,
  compareHref,
  marketChange,
  roleKeysFor,
  parseCompareIds,
  type PlayerProfile,
  roleSeries,
  withPlayer,
  withoutPlayer,
} from "./profile";

const base: PlayerProfile = {
  gsis_id: "a",
  full_name: "A",
  position: "WR",
  week: 9,
  result_week: null,
  result_points: null,
  is_out: false,
  projection: 11,
  p10: 4,
  median: 12,
  p90: 21,
  chance_to_play: 1,
  injury: null,
  injury_note: null,
  ros_points: 80,
  replacement_name: "Free Guy",
  replacement_points: 62.5,
  ros_over_replacement: 17.5,
  outlook_label: null,
  why: null,
  role_weeks: [],
  next_game: null,
  bye_week: null,
};

describe("answerSentence", () => {
  it("leads with the next game median and range", () => {
    expect(answerSentence(base)).toBe("Median 12.0 points in week 9, likely between 4.0 and 21.0.");
  });
  it("adds the chance to play when it is below certain", () => {
    expect(answerSentence({ ...base, chance_to_play: 0.76 })).toBe(
      "Median 12.0 points in week 9, likely between 4.0 and 21.0. 76% to play.",
    );
  });
  it("falls back to rest of season over replacement", () => {
    expect(answerSentence({ ...base, median: null, p10: null, p90: null })).toBe("+17.5 points over Free Guy for the rest of the season.");
    expect(answerSentence({ ...base, median: null, ros_over_replacement: -3 })).toBe(
      "-3.0 points against Free Guy for the rest of the season.",
    );
  });
  it("is null with nothing to say", () => {
    expect(answerSentence({ ...base, median: null, ros_over_replacement: null })).toBeNull();
  });
});

describe("final games, out players, role and market rules", () => {
  it("leads with the final result and adds the next week's range", () => {
    expect(answerSentence({ ...base, result_week: 8, result_points: 17.3, week: 9 })).toBe(
      "Week 8: 17.3 points, final. Median 12.0 points in week 9, likely between 4.0 and 21.0.",
    );
    expect(answerSentence({ ...base, result_week: 8, result_points: 17.3, week: null, median: null, p10: null, p90: null })).toBe(
      "Week 8: 17.3 points, final.",
    );
  });
  it("says an out player's rest of season value is if he returns", () => {
    expect(answerSentence({ ...base, median: null, is_out: true })).toMatch(/He is out/);
  });
  it("hides target share for a QB and both shares for K and DEF", () => {
    expect(roleKeysFor("QB")).toEqual(["snap_share"]);
    expect(roleKeysFor("WR")).toEqual(["snap_share", "target_share"]);
    expect(roleKeysFor("K")).toEqual([]);
    expect(roleKeysFor("DEF")).toEqual([]);
  });
  it("gives a market change only when the value 30 days ago was positive", () => {
    expect(marketChange(600, 620)).toBeNull();
    expect(marketChange(600, null)).toBeNull();
    expect(marketChange(600, -150)?.percent).toBeCloseTo(-0.2);
  });
});

describe("roleSeries", () => {
  it("keeps the weeks that have a value, in order, as percentages", () => {
    const weeks = [
      { week: 1, snap_share: 0.8, target_share: null },
      { week: 2, snap_share: 0.6, target_share: 0.25 },
    ];
    expect(roleSeries(weeks, "snap_share")).toEqual([80, 60]);
    expect(roleSeries(weeks, "target_share")).toEqual([25]);
    expect(roleSeries([], "snap_share")).toEqual([]);
  });
});

describe("compare ids", () => {
  it("reads up to three distinct ids from repeated p params", () => {
    expect(parseCompareIds(new URLSearchParams("p=a&p=b&p=a&p=c&p=d&p="))).toEqual(["a", "b", "c"]);
  });
  it("adds and removes players, never past three or twice", () => {
    expect(withPlayer(["a", "b", "c"], "d")).toEqual(["a", "b", "c"]);
    expect(withPlayer(["a"], "a")).toEqual(["a"]);
    expect(withPlayer(["a"], "b")).toEqual(["a", "b"]);
    expect(withoutPlayer(["a", "b"], "a")).toEqual(["b"]);
  });
  it("builds the compare link keeping league, team and week", () => {
    expect(compareHref(["a", "b"], "?league=L&team=2&week=5&s=x")).toBe("/players/compare?league=L&team=2&week=5&p=a&p=b");
    expect(compareHref([], "")).toBe("/players/compare");
  });
});
