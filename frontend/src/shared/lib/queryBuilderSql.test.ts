import { describe, expect, it } from "vitest";

import { buildFilterWhereSql } from "./queryBuilderSql";

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
