import { describe, expect, it } from "vitest";

import { buildFilterWhereSql, buildStatQueryPlans } from "./queryBuilderSql";

const planParams = {
  filterChipState: {},
  gsisIds: ["00-0033873"],
  viewNames: ["nfl_pbp_2023"],
  granularity: "total" as const,
  minPlays: 0,
};

describe("buildStatQueryPlans play filters", () => {
  it("leaves sack rows out of attempt-based stats", () => {
    const [plan] = buildStatQueryPlans({ ...planParams, statIds: ["pass_yards"] });

    expect(plan!.sql).toContain("main.sack = 0");
  });

  it("keeps sack rows for stats that count them", () => {
    const [plan] = buildStatQueryPlans({ ...planParams, statIds: ["pass_sack_rate"] });

    expect(plan!.sql).not.toContain("main.sack = 0");
  });

  it("runs stats with different row filters as separate queries", () => {
    const plans = buildStatQueryPlans({ ...planParams, statIds: ["pass_yards", "pass_sack_rate"] });

    expect(plans.map((p) => p.statIdsOrdered)).toEqual([["pass_yards"], ["pass_sack_rate"]]);
  });

  it("keeps stats that share a filter in one query", () => {
    const plans = buildStatQueryPlans({ ...planParams, statIds: ["pass_yards", "cmp_pct"] });

    expect(plans).toHaveLength(1);
    expect(plans[0]!.statIdsOrdered).toEqual(["pass_yards", "cmp_pct"]);
  });

  it("does not count a sack as both a row and an extra dropback", () => {
    const [plan] = buildStatQueryPlans({ ...planParams, statIds: ["pass_any_a"] });

    expect(plan!.sql).not.toMatch(/COUNT\(\*\) \+ SUM\(main\.sack\)/);
  });
});

describe("buildFilterWhereSql", () => {
  it("returns an empty string when no chip is on", () => {
    expect(buildFilterWhereSql({})).toBe("");
  });

  it("limits the 3-or-fewer rushers chip to pass plays", () => {
    // Run plays carry a real 0 for rushers, so without this the chip matches nearly every run.
    const sql = buildFilterWhereSql({ "pr-lte3": true });

    expect(sql).toContain("play_type = 'pass'");
    expect(sql).toContain("number_of_pass_rushers <= 3");
  });

  it("filters on a season the data has", () => {
    expect(buildFilterWhereSql({ "season-2026": true })).toBe("((season = 2026))");
  });

  it("joins chips from different groups with AND and chips in a group with OR", () => {
    const sql = buildFilterWhereSql({ "down-1": true, "down-3": true, "qtr-4": true });

    expect(sql).toBe("((down = 1) OR (down = 3)) AND ((qtr = 4))");
  });
});
