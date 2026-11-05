import { describe, expect, test } from "vitest";
import { firstKickoff, matchupStatus, orderedSides, sideName, sideScore, sortMineFirst } from "./scoreboard";
import { row, side } from "./scoreboardFixtures";

describe("scoreboard logic", () => {
  test("puts the viewed team first and marks it in text", () => {
    const r = row({ is_me: false }, { is_me: true });
    expect(orderedSides(r)[0].team_name).toBe("Theirs");
    expect(sideName(orderedSides(r)[0])).toBe("Theirs (you)");
  });
  test("keeps order when neither or the first side is mine", () => {
    expect(orderedSides(row())[0].team_name).toBe("Mine");
    expect(orderedSides(row({ is_me: true }))[0].team_name).toBe("Mine");
  });
});

describe("sideScore", () => {
  test("a final shows points and no win chance", () => {
    expect(sideScore(side({ points: 148.5, win_prob: null }), "Final")).toEqual({ value: "148.5", unit: "final", win: null });
  });
  test("a live game shows points so far with the projected final and win chance", () => {
    expect(sideScore(side({ points: 24.1, projected: 110, win_prob: 0.6 }), "Live")).toEqual({ value: "24.1", unit: "so far", win: "60%", projected: "110.0" });
  });
  test("an upcoming game shows the projection and win chance", () => {
    expect(sideScore(side({ projected: 110, win_prob: 0.6 }), "Not started")).toEqual({ value: "110.0", unit: "proj", win: "60%" });
  });
});

describe("matchupStatus", () => {
  test("names final and live, and the first kickoff for an upcoming matchup", () => {
    expect(matchupStatus("Final", null)).toBe("Final");
    expect(matchupStatus("Live", null)).toBe("Live");
    expect(matchupStatus("Not started", null)).toBe("Not started");
    expect(matchupStatus("Not started", new Date("2026-11-08T18:00:00Z"))).toBe("Sun 1:00 PM");
  });
  test("the first kickoff is the earliest timed one", () => {
    const k = [{ team: "A", kickoff: "2026-11-08T18:00:00Z" }, { team: "B", kickoff: null }, { team: "C", kickoff: "2026-11-06T01:15:00Z" }];
    expect(firstKickoff(k)?.toISOString()).toBe("2026-11-06T01:15:00.000Z");
    expect(firstKickoff([])).toBeNull();
  });
});

describe("sortMineFirst", () => {
  test("moves my matchup to the top and keeps the rest in order", () => {
    const rows = [row({ team_name: "A" }), row({ team_name: "B", is_me: true }), row({ team_name: "C" })];
    expect(sortMineFirst(rows).map((r) => r.a.team_name)).toEqual(["B", "A", "C"]);
    expect(rows.map((r) => r.a.team_name)).toEqual(["A", "B", "C"]);
  });
});
