/**
 * The Parquet loader against a real shard in Node. Skipped when the data is not built (as in CI).
 */
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { asyncBufferFromFile } from "hyparquet";
import { compressors } from "hyparquet-compressors";
import { describe, expect, it } from "vitest";

import { createParquetLoader } from "./parquetColumns";

const SHARD = fileURLToPath(new URL("../../../../backend/data/nfl_pbp_2023.parquet", import.meta.url));
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
