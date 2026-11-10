import { describe, expect, it } from "vitest";

import { settleStats } from "./settleStats";

describe("settleStats", () => {
  it("reads generic EPA and success as the rusher's or receiver's own", () => {
    expect(settleStats(["eff_epa"], { kind: "players", positions: ["RB"] })).toEqual(["rush_epa"]);
    expect(settleStats(["eff_success"], { kind: "players", positions: ["TE"] })).toEqual(["rec_success"]);
    expect(settleStats(["pass_adot"], { kind: "players", positions: ["WR"] })).toEqual(["rec_adot"]);
  });

  it("keeps the passer's stat for a quarterback and for players of different roles", () => {
    expect(settleStats(["eff_epa"], { kind: "players", positions: ["QB"] })).toEqual(["eff_epa"]);
    expect(settleStats(["eff_epa"], { kind: "players", positions: ["QB", "RB"] })).toEqual(["eff_epa"]);
  });

  it("keeps a stat named by role", () => {
    expect(settleStats(["rush_epa"], { kind: "players", positions: ["QB"] })).toEqual(["rush_epa"]);
    expect(settleStats(["rush_epa"], { kind: "team" })).toEqual(["rush_epa"]);
  });

  it("reads generic EPA for a team over every play", () => {
    expect(settleStats(["eff_epa", "eff_success", "pass_yards"], { kind: "team" })).toEqual(["team_epa", "team_success", "pass_yards"]);
  });

  it("turns a team stat asked of a player into the player's own", () => {
    expect(settleStats(["team_epa"], { kind: "players", positions: ["RB"] })).toEqual(["rush_epa"]);
    expect(settleStats(["team_epa"], { kind: "players", positions: [] })).toEqual(["eff_epa"]);
  });
});
