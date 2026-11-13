import { describe, expect, it } from "vitest";
import { playoffWeeksOf } from "./logic";

describe("playoffWeeksOf", () => {
  it("spans the league's playoff weeks", () => {
    expect(playoffWeeksOf({ playoff_week_start: 15, playoff_weeks: 3 })).toEqual({ first: 15, last: 17 });
  });
  it("is null until the league's playoff weeks are known", () => {
    expect(playoffWeeksOf(undefined)).toBeNull();
    expect(playoffWeeksOf({ playoff_week_start: null, playoff_weeks: 3 })).toBeNull();
    expect(playoffWeeksOf({ playoff_week_start: 15, playoff_weeks: null })).toBeNull();
    expect(playoffWeeksOf({ playoff_week_start: 15, playoff_weeks: 0 })).toBeNull();
  });
});
