import { canEvaluate, formatSigned, formatValue, MAX_TRADE_IDS, sideMeasures, toggleId, toRequest, tradeKey } from "./logic";

describe("toggleId", () => {
  it("adds, removes and never mutates", () => {
    const base = ["a"] as const;
    expect(toggleId(base, "b")).toEqual(["a", "b"]);
    expect(toggleId(base, "a")).toEqual([]);
    expect(base).toEqual(["a"]);
  });
  it("stops at the id cap but still allows removal", () => {
    const full = Array.from({ length: MAX_TRADE_IDS }, (_, i) => `p${i}`);
    expect(toggleId(full, "extra")).toBe(full);
    expect(toggleId(full, "p0")).toHaveLength(MAX_TRADE_IDS - 1);
  });
});

describe("requests", () => {
  it("needs a partner and both sides", () => {
    expect(canEvaluate({ partner: null, give: ["a"], get: ["b"] })).toBe(false);
    expect(canEvaluate({ partner: 3, give: [], get: ["b"] })).toBe(false);
    expect(toRequest({ partner: 3, give: ["a"], get: ["b"] })).toEqual({ partner_roster_id: 3, give_ids: ["a"], get_ids: ["b"] });
    expect(toRequest({ partner: 0, give: [], get: [] })).toBeNull();
  });
  it("keys a trade by its sorted ids", () => {
    expect(tradeKey({ partner: 1, give: ["b", "a"], get: ["c"] })).toBe(tradeKey({ partner: 1, give: ["a", "b"], get: ["c"] }));
  });
});

describe("formatting", () => {
  it("scales probabilities to points", () => {
    const side = { side: "me", roster_id: 1, team_name: "T", playoff_before: 0.5, playoff_after: 0.523, title_before: 0.1, title_after: 0.09, wins_before: 8, wins_after: 8.25 };
    const [playoff, title, wins] = sideMeasures(side);
    expect(formatValue(playoff.after, playoff.percent)).toBe("52.3%");
    expect(formatSigned(title.after - title.before, true)).toBe("-1.0%");
    expect(formatSigned(wins.after - wins.before, false)).toBe("+0.3");
  });
  it("never prints -0.0", () => {
    expect(formatSigned(-0.01, true)).toBe("0.0%");
  });
});
