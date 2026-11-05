import { describe, expect, it } from "vitest";

import { buildFilterChipGroups } from "@/stat/config/queryBuilderOptions";

import { dataThrough, participationGap } from "./dataFreshness";
import { manifestSchema } from "./schemas/manifest";

function manifest(seasons: { season: number; max_week: number | null; has_participation: boolean }[]) {
  return manifestSchema.parse({
    schema_version: 1,
    built_at: "2026-11-04T12:00:00+00:00",
    nflreadpy_version: "0.1.0",
    seasons: seasons.map((s) => ({ ...s, path: `nfl_pbp_${s.season}.parquet`, rows: 1 })),
    player_index: null,
  });
}

const DATA = manifest([
  { season: 2025, max_week: 22, has_participation: true },
  { season: 2026, max_week: 8, has_participation: false },
]);
const chipGroups = buildFilterChipGroups([2025, 2026]);

describe("dataThrough", () => {
  it("names the latest season and week", () => {
    expect(dataThrough(DATA)).toBe("2026 week 8");
  });

  it("names just the season when no week is known", () => {
    expect(dataThrough(manifest([{ season: 2026, max_week: null, has_participation: false }]))).toBe("2026");
  });

  it("is null before the data is loaded or when there are no seasons", () => {
    expect(dataThrough(null)).toBeNull();
    expect(dataThrough(manifest([]))).toBeNull();
  });
});

describe("participationGap", () => {
  const gap = (filters: string[]) => participationGap({ manifest: DATA, filters, chipGroups });

  it("is null when no participation filter is on", () => {
    expect(gap(["down-3", "season-2026"])).toBeNull();
  });

  it("lists the seasons without participation data when such a filter meets them", () => {
    expect(gap(["pers-11", "season-2026"])).toEqual({ seasons: [2026], chips: ["pers-11"] });
  });

  it("looks at every season when no season chip is on", () => {
    expect(gap(["dib-gte7"])).toEqual({ seasons: [2026], chips: ["dib-gte7"] });
  });

  it("is null when the chosen seasons all have participation data", () => {
    expect(gap(["pr-gte4", "season-2025"])).toBeNull();
  });

  it("only mentions the seasons the query covers", () => {
    expect(gap(["pers-12", "season-2025", "season-2026"])?.seasons).toEqual([2026]);
  });

  it("is null before the data is loaded", () => {
    expect(participationGap({ manifest: null, filters: ["pers-11"], chipGroups })).toBeNull();
  });
});
