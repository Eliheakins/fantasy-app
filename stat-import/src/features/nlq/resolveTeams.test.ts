import { describe, expect, it } from "vitest";

import { dropTeamNames, resolveTeams } from "./resolveTeams";

const ids = (question: string) => resolveTeams(question).map((m) => m.id);

describe("resolveTeams", () => {
  it.each([
    ["Chiefs passing yards in 2023", ["KC"]],
    ["Kansas City Chiefs passing yards in 2023", ["KC"]],
    ["49ers rushing yards", ["SF"]],
    ["Patriots and Bills rushing yards", ["NE", "BUF"]],
    ["passing yards allowed by the Green Bay Packers", ["GB"]],
  ])("finds the teams in %s", (question, expected) => {
    expect(ids(question)).toEqual(expected);
  });

  it("never reads an abbreviation that is also a word", () => {
    expect(ids("no passing yards in LA")).toEqual([]);
  });

  it("gives the token span of each match, so the parser can mark it read", () => {
    expect(resolveTeams("Kansas City Chiefs passing yards")).toEqual([{ id: "KC", start: 0, length: 3 }]);
  });
});

describe("dropTeamNames", () => {
  const match = (phrase: string, start: number) => ({ phrase, start, candidates: [] });

  it("drops a player matched only by a word that names a team", () => {
    const question = "Chiefs and Bills rushing yards";

    expect(dropTeamNames([match("bills", 2)], resolveTeams(question))).toEqual([]);
  });

  it("keeps a player named in full, even if part of the name is a team", () => {
    const question = "Keaton Bills snaps";

    expect(dropTeamNames([match("keaton bills", 0)], resolveTeams(question))).toHaveLength(1);
  });
});
