// @vitest-environment node
/**
 * The Parquet loader against a real shard in Node. Skipped when the data is not built (as in CI).
 */
import { existsSync } from "node:fs";
import { resolve } from "node:path";

import { asyncBufferFromFile } from "hyparquet";
import { compressors } from "hyparquet-compressors";
import { describe, expect, it } from "vitest";

import { createParquetLoader } from "./parquetColumns";

describe("createParquetLoader errors", () => {
  it("names the season and file, and says where to look, when the file cannot be read", async () => {
    const failing = createParquetLoader(async () => {
      throw new Error("Failed to fetch");
    });

    const error = (await failing({ year: 2024, url: "https://cdn.example.com/nfl_pbp_2024.parquet" }, "yards_gained").catch(
      (e: Error) => e,
    )) as Error;

    expect(error.message).toContain("2024");
    expect(error.message).toContain("https://cdn.example.com/nfl_pbp_2024.parquet");
    expect(error.message).toContain("Failed to fetch");
  });

  it("retries opening the file on the next query after a failure", async () => {
    let calls = 0;
    const flaky = createParquetLoader(async () => {
      calls++;
      throw new Error("down");
    });
    const source = { year: 2024, url: "http://x/a.parquet" };

    await flaky(source, "a").catch(() => undefined);
    await flaky(source, "a").catch(() => undefined);

    expect(calls).toBe(2);
  });
});

const SHARD = resolve(import.meta.dirname, "../../../../data/stat/nfl_pbp_2023.parquet");
const source = { year: 2023, url: SHARD };
const load = createParquetLoader((s) => asyncBufferFromFile(s.url), compressors);

describe.skipIf(!existsSync(SHARD))("createParquetLoader", () => {
  it("reads a column across the whole file", async () => {
    const yards = await load(source, "yards_gained");
    const ids = await load(source, "passer_player_id");

    expect(yards.length).toBeGreaterThan(30000);
    expect(ids.length).toBe(yards.length);
  });

  it("gives an all-null column for one the file lacks, as a UNION BY NAME would", async () => {
    const missing = await load(source, "a_column_older_seasons_never_had");
    const known = await load(source, "yards_gained");

    expect(missing.length).toBe(known.length);
    expect(Array.from(missing).every((v) => v === null)).toBe(true);
  });
});
