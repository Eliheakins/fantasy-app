import { describe, expect, it } from "vitest";

import { buildFilterChipGroups, getAllFilterChipIds } from "./queryBuilderOptions";

const seasonGroup = (seasons: number[]) => buildFilterChipGroups(seasons).find((g) => g.id === "season");

describe("buildFilterChipGroups", () => {
  it("makes one season chip per season, oldest first, with a matching predicate", () => {
    const group = seasonGroup([2024, 2022, 2023]);

    expect(group?.options).toEqual([
      { id: "season-2022", label: "2022", predicate: "season = 2022" },
      { id: "season-2023", label: "2023", predicate: "season = 2023" },
      { id: "season-2024", label: "2024", predicate: "season = 2024" },
    ]);
  });

  it("includes a season as soon as the data has it, with no code change", () => {
    expect(seasonGroup([2025, 2026])?.options.map((o) => o.id)).toEqual(["season-2025", "season-2026"]);
  });

  it("drops duplicate seasons", () => {
    expect(seasonGroup([2023, 2023])?.options).toHaveLength(1);
  });

  it("omits the season group when there are no seasons", () => {
    expect(seasonGroup([])).toBeUndefined();
  });

  it("keeps the season group where it was among the other groups", () => {
    const ids = buildFilterChipGroups([2023]).map((g) => g.id);

    expect(ids.indexOf("season")).toBe(ids.indexOf("ydstogo") + 1);
  });

  it("gives every chip a unique id", () => {
    const ids = getAllFilterChipIds(buildFilterChipGroups([2021, 2022, 2023]));

    expect(new Set(ids).size).toBe(ids.length);
  });
});
