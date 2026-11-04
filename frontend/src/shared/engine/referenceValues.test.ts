/**
 * Runs the engine in Node over the built Parquet shards and checks every metric against the
 * reference values recorded in `metrics/metrics.json` (official nflverse totals). These are the
 * same figures the Python tests check against DuckDB, so the two engines are held to one standard.
 *
 * Skipped for any season whose shard is not built (as in CI). Build with `uv run python backend/scripts/build_data.py`.
 */
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { asyncBufferFromFile } from "hyparquet";
import { compressors } from "hyparquet-compressors";
import { describe, expect, it } from "vitest";

import { buildFilterChipGroups } from "@/shared/config/queryBuilderOptions";
import rawMetrics from "../../../../metrics/metrics.json";
import { parseMetricsFile } from "@/shared/lib/schemas/metrics";

import { ColumnStore } from "./columns";
import { createParquetLoader } from "./parquetColumns";
import { runStatQuery } from "./statQuery";

const DATA_DIR = fileURLToPath(new URL("../../../../backend/data/", import.meta.url));
const shardPath = (season: number) => `${DATA_DIR}nfl_pbp_${season}.parquet`;

const store = new ColumnStore(
  createParquetLoader((source) => asyncBufferFromFile(source.url), compressors),
);

const cases = parseMetricsFile(rawMetrics).metrics.flatMap((m) =>
  m.reference_values.map((ref) => ({ metric: m, ref })),
);

describe("reference values", () => {
  it("has reference values to check", () => {
    expect(cases.length).toBeGreaterThanOrEqual(15);
  });

  for (const { metric, ref } of cases) {
    const name = `${metric.id} for ${ref.player} ${ref.season} ${ref.season_type}`;

    it.skipIf(!existsSync(shardPath(ref.season)))(`${name} matches ${ref.value}`, async () => {
      const result = await runStatQuery(
        {
          statIds: [metric.id],
          filterChipState: {
            [`season-${ref.season}`]: true,
            [ref.season_type === "REG" ? "stype-reg" : "stype-post"]: true,
          },
          gsisIds: [ref.gsis_id],
          sources: [{ year: ref.season, url: shardPath(ref.season) }],
          granularity: "total",
          minPlays: 0,
          chipGroups: buildFilterChipGroups([ref.season]),
        },
        store,
      );

      const value = Number(result.rows[0]?.[`m_${metric.id}`]);
      expect(Math.abs(value - ref.value)).toBeLessThanOrEqual(Math.abs(ref.value) * ref.tolerance);
    });
  }
});
