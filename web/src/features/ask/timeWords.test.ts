import { describe, expect, it } from "vitest";

import { timeOf } from "./paths/queryStates";
import { readTime, withTime } from "./timeWords";

const SCOPE = { seasons: [2021, 2022, 2023, 2024, 2025, 2026], maxWeeks: { 2024: 22, 2025: 22, 2026: 8 } };
const read = (q: string) => readTime(q, SCOPE);

describe("readTime", () => {
  it("reads relative seasons against the latest season in the data", () => {
    expect(read("Saquon rushing yards this season").filters).toEqual(["season-2026"]);
    expect(read("Chase receiving yards last year").filters).toEqual(["season-2025"]);
    expect(read("saquon rushin yards this szn").filters).toEqual(["season-2026"]);
    expect(read("Allen passing yards two seasons ago").filters).toEqual(["season-2024"]);
  });

  it("reads single weeks, ranges and since-week against the season named", () => {
    expect(read("Josh Allen passing yards in week 3 2025").filters).toEqual(["wk-3"]);
    expect(read("Allen passing yards weeks 3 to 5").filters).toEqual(["wk-3", "wk-4", "wk-5"]);
    expect(read("Allen passing yards weeks 3-5").filters).toEqual(["wk-3", "wk-4", "wk-5"]);
    expect(read("Allen passing yards from week 3 to week 4").filters).toEqual(["wk-3", "wk-4"]);
    // The current season reaches week 8, so "since week 5" is weeks 5 to 8.
    expect(read("Malik Nabers receptions since week 5").filters).toEqual(["wk-5", "wk-6", "wk-7", "wk-8"]);
    expect(read("Nabers receptions after week 6 this season").filters).toEqual(["season-2026", "wk-7", "wk-8"]);
  });

  it("reads last week as the latest week in the data and says so", () => {
    const time = read("Ja'Marr Chase PPR points last week");

    expect(time.filters).toEqual(["season-2026", "wk-8"]);
    expect(time.notes[0]).toMatch(/week 8 of 2026/);
  });

  it("reads last N games, in digits or words", () => {
    expect(read("Chase receiving yards last 3 games").lastGames).toBe(3);
    expect(read("Chase receiving yards in his last three games").lastGames).toBe(3);
    expect(read("Chase receiving yards last game").lastGames).toBe(1);
  });

  it("reads career as every season on purpose", () => {
    expect(read("Josh Allen career passing touchdowns").career).toBe(true);
  });

  it("refuses a week the data has not reached", () => {
    expect(read("Allen passing yards week 12").problem).toMatch(/reaches week 8/);
  });

  it("gives the model the question without the words it read", () => {
    expect(read("Malik Nabers receptions since week 5").rest).toBe("malik nabers receptions");
    expect(read("Mahomes passing yards 2025").rest).toBe("Mahomes passing yards 2025");
  });

  it("leaves other numbers and words alone", () => {
    const time = read("top 5 rushers in yards per carry 2025");

    expect(time.filters).toEqual([]);
    expect(time.used).toEqual([]);
  });

  it("puts code-read seasons and weeks in place of the model's own", () => {
    const time = read("Josh Allen passing yards in week 3 2025");

    expect(withTime(["season-2025", "week-early"], time)).toEqual(["season-2025", "wk-3"]);
  });
});

describe("timeOf", () => {
  it("uses the current season when none is named, and says so", () => {
    const time = timeOf([], "Mahomes yards", SCOPE, null);

    expect(time.filters).toEqual(["season-2026", "stype-reg"]);
    expect(time.notes[0]).toMatch(/2026, the current season/);
  });

  it("keeps every season for career, a split by season, and rare situations", () => {
    expect(timeOf([], "Josh Allen career passing touchdowns", SCOPE, null).filters).toEqual(["stype-reg"]);
    expect(timeOf([], "St. Brown receiving yards by season", SCOPE, "season").filters).toEqual(["stype-reg"]);
    expect(timeOf(["stype-post"], "Kelce receptions in the playoffs", SCOPE, null).filters).toEqual(["stype-post"]);
  });

  it("reads last N games in the current season", () => {
    const time = timeOf([], "Chase receiving yards last 3 games", SCOPE, null);

    expect(time).toMatchObject({ lastGames: 3, filters: ["season-2026", "stype-reg"] });
  });
});
