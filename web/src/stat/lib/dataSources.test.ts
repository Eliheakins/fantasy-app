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
  it("addresses each manifest season from the data base URL, stamped with the build time so a rebuilt shard is not read from cache", () => {
    expect(seasonSources(manifest)).toEqual([
      { year: 2025, url: "/api/stat/data/nfl_pbp_2025.parquet?v=2026-11-04T12%3A00%3A00%2B00%3A00" },
      { year: 2026, url: "/api/stat/data/nfl_pbp_2026.parquet?v=2026-11-04T12%3A00%3A00%2B00%3A00" },
    ]);
  });

  it("is empty before the manifest has loaded", () => {
    expect(seasonSources(null)).toEqual([]);
  });
});
