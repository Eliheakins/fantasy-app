// @vitest-environment node
/**
 * Runs the engine in Node over the built Parquet shards and checks every metric against the
 * reference values recorded in `metrics/metrics.json` (official nflverse totals). These are the
 * same figures the Python tests check against DuckDB, so the two engines are held to one standard.
 *
 * Skipped for any season whose shard is not built (as in CI). Build with `make stat-data`.
 */
import { existsSync } from "node:fs";
import { resolve } from "node:path";

import { asyncBufferFromFile } from "hyparquet";
import { compressors } from "hyparquet-compressors";
import { describe, expect, it } from "vitest";

import { buildFilterChipGroups } from "@/stat/config/queryBuilderOptions";
import { getStatById } from "@/stat/config/statDictionary";
import rawMetrics from "../../../../metrics/metrics.json";
import { parseMetricsFile } from "@/stat/lib/schemas/metrics";

import { ColumnStore } from "./columns";
import { createParquetLoader } from "./parquetColumns";
import { runStatQuery } from "./statQuery";

const DATA_DIR = `${resolve(import.meta.dirname, "../../../../data/stat")}/`;
const shardPath = (season: number) => `${DATA_DIR}nfl_pbp_${season}.parquet`;
const PLAYER_GAME_PATH = `${DATA_DIR}player_game.parquet`;

const store = new ColumnStore(createParquetLoader((source) => asyncBufferFromFile(source.url), compressors));

const cases = parseMetricsFile(rawMetrics).metrics.flatMap((m) => m.reference_values.map((ref) => ({ metric: m, ref })));

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

describe("reference values served from the player-game table", () => {
  const tierOne = cases.filter(({ metric }) => getStatById(metric.id)?.playerGameColumn);

  it("covers the counting stats that have official totals", () => {
    expect(tierOne.length).toBeGreaterThanOrEqual(8);
  });

  for (const { metric, ref } of tierOne) {
    const name = `${metric.id} for ${ref.player} ${ref.season} ${ref.season_type}`;

    it.skipIf(!existsSync(PLAYER_GAME_PATH))(`${name} matches ${ref.value} without reading any play shard`, async () => {
      const reads: string[] = [];
      const tierStore = new ColumnStore(async (source, column) => {
        reads.push(source.url);
        return createParquetLoader((s) => asyncBufferFromFile(s.url), compressors)(source, column);
      });
      const result = await runStatQuery(
        {
          statIds: [metric.id],
          filterChipState: {
            [`season-${ref.season}`]: true,
            [ref.season_type === "REG" ? "stype-reg" : "stype-post"]: true,
          },
          gsisIds: [ref.gsis_id],
          sources: [{ year: ref.season, url: shardPath(ref.season) }],
          playerGame: { year: 0, url: PLAYER_GAME_PATH },
          granularity: "total",
          minPlays: 0,
          chipGroups: buildFilterChipGroups([ref.season]),
        },
        tierStore,
      );

      const value = Number(result.rows[0]?.[`m_${metric.id}`]);
      expect(Math.abs(value - ref.value)).toBeLessThanOrEqual(Math.abs(ref.value) * ref.tolerance);
      expect(new Set(reads)).toEqual(new Set([PLAYER_GAME_PATH]));
    });
  }
});
