import { describe, expect, it } from "vitest";
import { answerSentence, compareHref, parseCompareIds, type PlayerProfile, roleSeries, withPlayer, withoutPlayer } from "./profile";

const base: PlayerProfile = {
  gsis_id: "a", full_name: "A", position: "WR", week: 9, projection: 11, p10: 4, median: 12, p90: 21, chance_to_play: 1,
  injury: null, injury_note: null, ros_points: 80, replacement_name: "Free Guy", replacement_points: 62.5,
  ros_over_replacement: 17.5, outlook_label: null, why: null, role_weeks: [],
};

describe("answerSentence", () => {
  it("leads with the next game median and range", () => {
    expect(answerSentence(base)).toBe("Median 12.0 points in week 9, likely between 4.0 and 21.0.");
  });
  it("adds the chance to play when it is below certain", () => {
    expect(answerSentence({ ...base, chance_to_play: 0.76 })).toBe("Median 12.0 points in week 9, likely between 4.0 and 21.0. 76% to play.");
  });
  it("falls back to rest of season over replacement", () => {
    expect(answerSentence({ ...base, median: null, p10: null, p90: null })).toBe("+17.5 points over Free Guy for the rest of the season.");
    expect(answerSentence({ ...base, median: null, ros_over_replacement: -3 })).toBe("-3.0 points against Free Guy for the rest of the season.");
  });
  it("is null with nothing to say", () => {
    expect(answerSentence({ ...base, median: null, ros_over_replacement: null })).toBeNull();
  });
});

describe("roleSeries", () => {
  it("keeps the weeks that have a value, in order, as percentages", () => {
    const weeks = [{ week: 1, snap_share: 0.8, target_share: null }, { week: 2, snap_share: 0.6, target_share: 0.25 }];
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
