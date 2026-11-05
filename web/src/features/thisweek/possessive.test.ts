import { possessive } from "@/lib/text";
import { neededLine } from "./gameDayText";

describe("possessive", () => {
  it("adds 's, or only an apostrophe after an s", () => {
    expect(possessive("Eli")).toBe("Eli's");
    expect(possessive("Theirs")).toBe("Theirs'");
    expect(possessive("Chris")).toBe("Chris'");
  });

  it("game-day text never builds Theirs's", () => {
    const c = { my_team: "Mine", opp_team: "Theirs", my_points: 50, opp_points: 40, opp_projected: 100, my_left: 2, opp_left: 1, points_needed: 20 };
    expect(neededLine(c)).toContain("Theirs' projected");
    expect(neededLine(c)).not.toContain("Theirs's");
  });
});
