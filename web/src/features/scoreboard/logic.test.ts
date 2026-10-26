import { describe, expect, test } from "vitest";
import {
  cardDomain,
  clampWeek,
  matchupTitle,
  orderedSides,
  pointsLine,
  winLabel,
} from "./logic";

import { row, side } from "./fixtures";

describe("scoreboard logic", () => {
  test("puts the viewed team first and marks it in text", () => {
    const r = row({ is_me: false }, { is_me: true });
    expect(orderedSides(r)[0].team_name).toBe("Theirs");
    expect(matchupTitle(r)).toBe("Theirs (you) versus Mine");
  });
  test("keeps order when neither or the first side is mine", () => {
    expect(orderedSides(row())[0].team_name).toBe("Mine");
    expect(orderedSides(row({ is_me: true }))[0].team_name).toBe("Mine");
  });
  test("one axis spans both sides", () => {
    const [lo, hi] = cardDomain(row({ floor: 60, ceiling: 100 }, { floor: 80, ceiling: 150 }))!;
    expect(lo).toBeLessThan(60);
    expect(hi).toBeGreaterThan(150);
  });
  test("points line follows the status", () => {
    const s = side();
    expect(pointsLine(s, "Not started")).toBe("Not started");
    expect(pointsLine(s, "Final")).toBe("24.1 pts final");
    expect(pointsLine(s, "Live")).toBe("24.1 pts so far, 50% of games left");
  });
  test("win label is null for a finished week", () => {
    expect(winLabel(side({ win_prob: null }), side({ win_prob: null }))).toBeNull();
    expect(winLabel(side(), side({ team_name: "Theirs", win_prob: 0.4 }))).toBe("Chance to win: Mine 60%, Theirs 40%");
  });
  test("clamps the week", () => {
    expect([clampWeek(0), clampWeek(7), clampWeek(30)]).toEqual([1, 7, 18]);
  });
});

import { hasMixedStatus, weekStatus } from "./logic";

describe("scoreboard labels", () => {
  test("names the week's state once and detects a mix", () => {
    expect(weekStatus([row(), row()])).toBe("live");
    expect(hasMixedStatus([row(), row({}, {}, { status: "Final" })])).toBe(true);
    expect(hasMixedStatus([row(), row()])).toBe(false);
  });
});
