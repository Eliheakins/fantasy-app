import { parseTeam, withTeam } from "./team";

describe("withTeam", () => {
  const roster = { path: { league: "a" } };
  it("sends nothing for the default team", () => {
    expect(withTeam("/api/leagues/{league}/roster", roster, null, "a")).toBe(roster);
  });
  it("adds team last to a league route's query", () => {
    expect(withTeam("/api/leagues/{league}/roster", roster, 3, "a")).toEqual({ path: { league: "a" }, query: { team: 3 } });
    const lineup = withTeam("/api/leagues/{league}/lineup", { path: { league: "a" }, query: { week: 2 } }, 3, "a");
    expect(Object.entries(lineup.query ?? {})).toEqual([
      ["week", 2],
      ["team", 3],
    ]);
  });
  it("leaves other leagues, the team list and global routes alone", () => {
    expect(withTeam("/api/leagues/{league}/roster", { path: { league: "b" } }, 3, "a")).toEqual({ path: { league: "b" } });
    expect(withTeam("/api/leagues/{league}/teams", roster, 3, "a")).toBe(roster);
    expect(withTeam("/api/status", {}, 3, "a")).toEqual({});
    expect(withTeam("/api/leagues", {}, 3, "a")).toEqual({});
  });
});

describe("parseTeam", () => {
  it("reads whole numbers only", () => {
    expect(parseTeam("12")).toBe(12);
    for (const bad of [null, "", "x", "-1", "1.5", "1e3"]) expect(parseTeam(bad)).toBeNull();
  });
});
