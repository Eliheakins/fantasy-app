import type { components } from "@/api/schema";
import { filterMoves, moveHeadline, rankMoves, tradeMoves, waiverMoves, worthMove } from "./moves";

type Waiver = components["schemas"]["WaiverRow"];
type Idea = components["schemas"]["MoveIdeaRow"];

const waiver = (name: string, over: Partial<Waiver> = {}): Waiver => ({
  gsis_id: `id-${name}`,
  full_name: name,
  position: "RB",
  drop_name: "Bernard",
  delta_points: 5,
  playoff_delta: 0.01,
  title_delta: 0.005,
  se_title: 0.002,
  trending_adds: null,
  ...over,
});
const idea = (over: Partial<Idea> = {}): Idea => ({
  kind: "trade",
  partner: "Rivals",
  give: "A",
  get: "B",
  give_ids: ["a"],
  get_ids: ["b"],
  rank: 1,
  playoff_delta: 0.02,
  title_delta: 0.01,
  se_title: 0.003,
  delta_points: 3,
  ...over,
});

const must = <T>(x: T | undefined): T => {
  if (x === undefined) throw new Error("missing");
  return x;
};

describe("waiverMoves", () => {
  it("shows the drop and says delta points are net of it", () => {
    const m = must(waiverMoves([waiver("Coleman", { playoff_delta: 0.023, delta_points: 4.2 })])[0]);
    expect(m.title).toBe("Add Coleman, drop Bernard");
    expect(m.drop).toEqual({ name: "Bernard", netPoints: 4.2 });
    expect(m.effect).toEqual({ playoffPoints: 2.3, points: 4.2 });
  });
  it("keeps a missing playoff change missing, not zero", () => {
    expect(must(waiverMoves([waiver("X", { playoff_delta: null })])[0]).effect.playoffPoints).toBeNull();
  });
});

describe("trending adds", () => {
  it("carries Sleeper's count on the move, or null without one", () => {
    const [hot, quiet] = waiverMoves([waiver("Hot", { trending_adds: 200000 }), waiver("Quiet")]).map(must);
    expect([must(hot).trendingAdds, must(quiet).trendingAdds]).toEqual([200000, null]);
  });
});

describe("tradeMoves", () => {
  it("keeps only trades and names the partner", () => {
    const out = tradeMoves([idea(), idea({ kind: "waiver", partner: null })]);
    expect(out).toHaveLength(1);
    const t = must(out[0]);
    expect(t.title).toBe("Trade A for B");
    expect(t.detail).toContain("Rivals");
    expect(t.drop).toBeNull();
  });
});

describe("rankMoves and filterMoves", () => {
  const all = [
    ...waiverMoves([waiver("Small", { playoff_delta: 0.005 }), waiver("PtsOnly", { playoff_delta: null, delta_points: 9 })]),
    ...tradeMoves([idea({ playoff_delta: 0.03 })]),
  ];
  it("ranks adds and trades together by playoff change, then points, without converting units", () => {
    expect(rankMoves(all).map((m) => m.title)).toEqual(["Trade A for B", "Add Small, drop Bernard", "Add PtsOnly, drop Bernard"]);
  });
  it("filters by view and does not change the input", () => {
    expect(filterMoves(all, "fa")).toHaveLength(2);
    expect(filterMoves(all, "trades")).toHaveLength(1);
    expect(filterMoves(all, "all")).toHaveLength(3);
  });
});

describe("worthMove and moveHeadline", () => {
  it("needs a playoff change of at least half a point", () => {
    const [big, small] = waiverMoves([waiver("Big", { playoff_delta: 0.005 }), waiver("Small", { playoff_delta: 0.004 })]).map(must);
    expect(worthMove(must(big))).toBe(true);
    expect(worthMove(must(small))).toBe(false);
  });
  it("answers with the top worthwhile move, else says none is worth it", () => {
    const [big, small] = waiverMoves([waiver("Big"), waiver("Small", { playoff_delta: 0.001 })]).map(must);
    expect(moveHeadline(big)).toBe("Add Big, drop Bernard");
    expect(moveHeadline(small)).toBe("No move is worth it this week");
    expect(moveHeadline(undefined)).toBe("No move is worth it this week");
  });
});
