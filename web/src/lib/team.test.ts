import { parseTeam, withTeam } from "./team";

describe("withTeam", () => {
  it("sends nothing for the default team", () => {
    expect(withTeam("/api/leagues/a/roster", null, "a")).toBe("/api/leagues/a/roster");
  });
  it("appends team to a league url, with ? or &", () => {
    expect(withTeam("/api/leagues/a/roster", 3, "a")).toBe("/api/leagues/a/roster?team=3");
    expect(withTeam("/api/leagues/a/lineup?week=2", 3, "a")).toBe("/api/leagues/a/lineup?week=2&team=3");
  });
  it("leaves other leagues, the team list and global routes alone", () => {
    expect(withTeam("/api/leagues/b/roster", 3, "a")).toBe("/api/leagues/b/roster");
    expect(withTeam("/api/leagues/a/teams", 3, "a")).toBe("/api/leagues/a/teams");
    expect(withTeam("/api/status", 3, "a")).toBe("/api/status");
    expect(withTeam("/api/leagues", 3, "a")).toBe("/api/leagues");
  });
  it("matches an encoded league key", () => {
    expect(withTeam("/api/leagues/a%20b/roster", 2, "a b")).toBe("/api/leagues/a%20b/roster?team=2");
  });
});

describe("parseTeam", () => {
  it("reads whole numbers only", () => {
    expect(parseTeam("12")).toBe(12);
    for (const bad of [null, "", "x", "-1", "1.5", "1e3"]) expect(parseTeam(bad)).toBeNull();
  });
});
