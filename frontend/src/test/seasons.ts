import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { manifestSchema } from "@/shared/lib/schemas/manifest";

const FIXTURE = fileURLToPath(
  new URL("../../../backend/tests/eval/manifest.fixture.json", import.meta.url),
);

/** Seasons from the fixture manifest, so tests and the exported eval catalog do not depend on local data. */
export const FIXTURE_SEASONS: number[] = manifestSchema
  .parse(JSON.parse(readFileSync(FIXTURE, "utf8")))
  .seasons.map((s) => s.season);
