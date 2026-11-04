import { afterEach, describe, expect, it } from "vitest";

import { useManifestStore } from "@/stores/useManifestStore";
import { useQueryBuilderStore } from "@/stores/useQueryBuilderStore";
import { FIXTURE_SEASONS } from "@/test/seasons";

import { getFilterChipGroups } from "./filterChipGroups";
import { buildStatQueryPlans } from "./queryBuilderSql";

const seasonIds = () =>
  getFilterChipGroups()
    .find((g) => g.id === "season")
    ?.options.map((o) => o.id) ?? [];

afterEach(() => {
  useManifestStore.setState({ seasons: FIXTURE_SEASONS });
  useQueryBuilderStore.getState().resetQueryBuilder();
});

describe("getFilterChipGroups", () => {
  it("follows the seasons in the manifest store", () => {
    useManifestStore.setState({ seasons: [2030] });

    expect(seasonIds()).toEqual(["season-2030"]);
  });

  it("has no season group before the manifest has loaded", () => {
    useManifestStore.setState({ seasons: [] });

    expect(seasonIds()).toEqual([]);
  });
});

describe("query builder store and the manifest's seasons", () => {
  it("resets the chip state to the seasons the data has", () => {
    useManifestStore.setState({ seasons: [2030] });

    useQueryBuilderStore.getState().resetQueryBuilder();

    const keys = Object.keys(useQueryBuilderStore.getState().filterChipState);
    expect(keys).toContain("season-2030");
    expect(keys).not.toContain("season-2021");
  });

  it("turns on only the chips an intent names that exist", () => {
    useQueryBuilderStore.getState().applyIntent({
      statIds: ["pass_yards"],
      filterIds: ["season-2023", "not-a-chip"],
      granularity: "total",
    });

    const state = useQueryBuilderStore.getState().filterChipState;
    expect(state["season-2023"]).toBe(true);
    expect(state["season-2024"]).toBe(false);
    expect("not-a-chip" in state).toBe(false);
  });
});

describe("rusher chip through the SQL builder", () => {
  it("qualifies the columns but not the 'pass' literal", () => {
    const [plan] = buildStatQueryPlans({
      statIds: ["pass_yards"],
      filterChipState: { "pr-lte3": true },
      gsisIds: ["00-0033873"],
      viewNames: ["nfl_pbp_2023"],
      granularity: "total",
      minPlays: 0,
    });

    expect(plan!.sql).toContain("main.play_type = 'pass' AND main.number_of_pass_rushers <= 3");
  });
});
