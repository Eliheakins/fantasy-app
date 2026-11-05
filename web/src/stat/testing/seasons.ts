import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { manifestSchema } from "@/stat/lib/schemas/manifest";

const FIXTURE = resolve(import.meta.dirname, "../../../../tests/stat/eval/manifest.fixture.json");

/** Seasons from the fixture manifest, so tests and the exported eval catalog do not depend on local data. */
export const FIXTURE_SEASONS: number[] = manifestSchema
  .parse(JSON.parse(readFileSync(FIXTURE, "utf8")))
  .seasons.map((s) => s.season);
