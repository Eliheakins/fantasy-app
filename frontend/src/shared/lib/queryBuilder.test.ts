import { describe, expect, it } from "vitest";

import { buildFilterChipGroups } from "@/shared/config/queryBuilderOptions";

import {
  buildFilterWhereSql,
  describeQuery,
  groupStatsByRows,
  mergeStatQueryResults,
  metricSelectAlias,
} from "./queryBuilder";

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

  it("can be limited to some groups", () => {
    const sql = buildFilterWhereSql(
      { "season-2023": true, "down-3": true, "stype-reg": true },
      { groups: buildFilterChipGroups([2023]), groupIds: ["season", "season_type"] },
    );

    expect(sql).toBe("((season = 2023)) AND ((season_type = 'REG'))");
  });
});

describe("groupStatsByRows", () => {
  const ids = (groups: { id: string }[][]) => groups.map((g) => g.map((s) => s.id));

  it("runs stats with different row filters as separate groups", () => {
    expect(ids(groupStatsByRows(["pass_yards", "pass_sack_rate"]))).toEqual([["pass_yards"], ["pass_sack_rate"]]);
  });

  it("keeps stats that share role, play type and filter together, in the order asked", () => {
    expect(ids(groupStatsByRows(["pass_yards", "cmp_pct", "pass_tds"]))).toEqual([["pass_yards", "cmp_pct", "pass_tds"]]);
  });

  it("separates roles and ignores unknown ids", () => {
    expect(ids(groupStatsByRows(["rush_yards", "nope", "rec_yards"]))).toEqual([["rush_yards"], ["rec_yards"]]);
  });
});

describe("mergeStatQueryResults", () => {
  it("joins groups on player and sorts by the first stat, nulls last", () => {
    const a = metricSelectAlias("pass_yards");
    const b = metricSelectAlias("pass_sack_rate");

    const merged = mergeStatQueryResults(
      [
        { columns: ["player_id", a], rows: [{ player_id: "x", [a]: 10 }, { player_id: "y", [a]: 30 }] },
        { columns: ["player_id", b], rows: [{ player_id: "x", [b]: 4 }, { player_id: "z", [b]: 9 }] },
      ],
      ["pass_yards", "pass_sack_rate"],
    );

    expect(merged.columns).toEqual(["player_id", a, b]);
    expect(merged.rows).toEqual([
      { player_id: "y", [a]: 30, [b]: null },
      { player_id: "x", [a]: 10, [b]: 4 },
      { player_id: "z", [a]: null, [b]: 9 },
    ]);
  });
});

describe("describeQuery", () => {
  it("lists each stat's definition and row filter, then the filters", () => {
    const text = describeQuery({
      statIds: ["pass_yards"],
      granularity: "per_game",
      filterChipState: { "down-3": true },
      minPlays: 20,
    });

    expect(text).toContain("Pass yards (per_game): SUM(yards_gained)");
    expect(text).toContain("only where complete_pass = 1 OR incomplete_pass = 1 OR interception = 1");
    expect(text).toContain("Filters: ((down = 3))");
    expect(text).toContain("Minimum rows per player: 20");
  });

  it("says when no filter is on", () => {
    expect(describeQuery({ statIds: ["rush_yards"], granularity: "total", filterChipState: {}, minPlays: 0 })).toContain(
      "Filters: none",
    );
  });
});
