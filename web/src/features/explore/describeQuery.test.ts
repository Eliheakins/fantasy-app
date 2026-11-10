import { describe, expect, it } from "vitest";

import { EMPTY_QUERY, type QueryState } from "@/stat/lib/queryUrl";

import { describeQuery } from "./describeQuery";

const words = { statNames: ["Targets"], seasonLabels: ["2026"] };
const base: QueryState = { ...EMPTY_QUERY, stats: ["rec_tgt"], granularity: "per_game" };

describe("describeQuery", () => {
  it("says a ranking in plain words", () => {
    const state: QueryState = { ...base, position: "WR", order: { metric: "rec_tgt", direction: "desc" }, limit: 25, minPlays: 20 };

    expect(describeQuery(state, words)).toBe("Top 25 wide receivers by Targets per game in 2026, at least 20 plays.");
  });

  it("lists the stats when nothing is ranked, and says every season when none is chosen", () => {
    const state: QueryState = { ...base, stats: ["rec_tgt", "rec_yards"] };

    expect(describeQuery(state, { statNames: ["Targets", "Receiving yards"], seasonLabels: [] })).toBe(
      "Targets and Receiving yards per game for players across every season.",
    );
  });

  it("asks for a stat first", () => {
    expect(describeQuery(EMPTY_QUERY, words)).toBe("Pick a stat to start.");
  });
});
