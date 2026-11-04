/**
 * Writes the stat/filter catalog the Ask feature sends to the model into the backend eval fixtures,
 * so `pytest -m eval` checks the real ids. Run: npm run export:catalog
 */
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { buildIntentCatalog } from "../src/shared/lib/nlqCatalog";
import { useManifestStore } from "../src/stores/useManifestStore";
import { FIXTURE_SEASONS } from "../src/test/seasons";

// The catalog lists the season chips, so pin the seasons to the fixture instead of local data.
useManifestStore.setState({ seasons: FIXTURE_SEASONS });

const target = fileURLToPath(new URL("../../backend/tests/eval/catalog.json", import.meta.url));
writeFileSync(target, `${JSON.stringify(buildIntentCatalog(), null, 2)}\n`);
process.stdout.write(`wrote ${target}\n`);
