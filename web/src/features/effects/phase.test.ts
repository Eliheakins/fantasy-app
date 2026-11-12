import { phaseOf } from "./phase";

const mine = (over = {}) => ({ is_me: true, as_of_week: 15, p_title: 0.2, p_playoffs: 1, ...over }) as never;
const league = { current_week: 15, playoff_week_start: 15 };

describe("phaseOf", () => {
  it("is season before the playoff start, whatever the odds", () => {
    expect(phaseOf({ ...league, current_week: 14 }, [mine({ p_title: 0 })])).toBe("season");
  });
  it("is season when the league has no playoff start or is not loaded", () => {
    expect(phaseOf({ current_week: 15, playoff_week_start: null }, [])).toBe("season");
    expect(phaseOf(undefined, [])).toBe("season");
  });
  it("is playoffs from the start week while my team can still win the title", () => {
    expect(phaseOf(league, [mine()])).toBe("playoffs");
    expect(phaseOf(league, [])).toBe("playoffs");
  });
  it("is out when my title odds are exactly 0 in a refresh from the playoffs", () => {
    expect(phaseOf(league, [mine({ p_title: 0 }), mine({ is_me: false, p_title: 0.5 })])).toBe("out");
  });
  it("does not call a team out from a refresh older than the playoff start", () => {
    expect(phaseOf(league, [mine({ p_title: 0, as_of_week: 14 })])).toBe("playoffs");
  });
});
