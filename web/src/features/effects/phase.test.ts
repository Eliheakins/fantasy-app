import { phaseOf } from "./phase";

const league = { current_week: 15, playoff_week_start: 15 };

describe("phaseOf", () => {
  it.each([
    ["regular", "season"],
    ["playing", "playoffs"],
    ["bye", "playoffs"],
    ["consolation", "playoffs"],
    ["eliminated", "out"],
    ["champion", "over"],
    ["over", "over"],
  ] as const)("maps team_phase %s to %s", (teamPhase, phase) => {
    expect(phaseOf({ ...league, team_phase: teamPhase })).toBe(phase);
  });
  it("reads a runner-up after the final as over, not out", () => {
    expect(phaseOf({ current_week: 18, playoff_week_start: 15, team_phase: "over" })).toBe("over");
  });
  it("falls back to the week when the phase is unknown, and is never out then", () => {
    expect(phaseOf({ ...league, team_phase: null })).toBe("playoffs");
    expect(phaseOf({ ...league, current_week: 17 })).toBe("playoffs");
    expect(phaseOf({ ...league, current_week: 14, team_phase: null })).toBe("season");
  });
  it("is season when the league has no playoff start or is not loaded", () => {
    expect(phaseOf({ current_week: 15, playoff_week_start: null })).toBe("season");
    expect(phaseOf(undefined)).toBe("season");
  });
});
