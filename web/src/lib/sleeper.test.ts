import { sleeperLeagueUrl } from "./sleeper";

describe("sleeperLeagueUrl", () => {
  it("builds the league page url", () => {
    expect(sleeperLeagueUrl("123456")).toBe("https://sleeper.com/leagues/123456");
  });
  it("encodes the id", () => {
    expect(sleeperLeagueUrl("a/b ?")).toBe("https://sleeper.com/leagues/a%2Fb%20%3F");
  });
});
