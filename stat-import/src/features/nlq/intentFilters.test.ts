import { describe, expect, it } from "vitest";

import { withDefaultSeasonType } from "./intentFilters";

describe("withDefaultSeasonType", () => {
  it("adds the regular season when no season type was named", () => {
    expect(withDefaultSeasonType(["season-2023"])).toEqual(["season-2023", "stype-reg"]);
    expect(withDefaultSeasonType([])).toEqual(["stype-reg"]);
  });

  it("leaves the filters alone when the playoffs were asked for", () => {
    expect(withDefaultSeasonType(["season-2023", "stype-post"])).toEqual(["season-2023", "stype-post"]);
  });

  it("leaves the filters alone when the regular season was named", () => {
    expect(withDefaultSeasonType(["stype-reg"])).toEqual(["stype-reg"]);
  });

  it("does not mutate its input", () => {
    const input = ["season-2023"];
    withDefaultSeasonType(input);

    expect(input).toEqual(["season-2023"]);
  });
});
