import { describe, expect, it } from "vitest";

import { seasonSources } from "./dataSources";
import { manifestSchema } from "./schemas/manifest";

const manifest = manifestSchema.parse({
  schema_version: 1,
  built_at: "2026-11-04T12:00:00+00:00",
  nflreadpy_version: "0.1.0",
  seasons: [
    { season: 2025, path: "nfl_pbp_2025.parquet", rows: 1, max_week: 22, has_participation: true },
    { season: 2026, path: "nfl_pbp_2026.parquet", rows: 1, max_week: 8, has_participation: false },
  ],
  player_index: null,
});

describe("seasonSources", () => {
  it("addresses each manifest season from the data base URL", () => {
    expect(seasonSources(manifest)).toEqual([
      { year: 2025, url: "http://localhost:8100/data/nfl_pbp_2025.parquet" },
      { year: 2026, url: "http://localhost:8100/data/nfl_pbp_2026.parquet" },
    ]);
  });

  it("is empty before the manifest has loaded", () => {
    expect(seasonSources(null)).toEqual([]);
  });
});
