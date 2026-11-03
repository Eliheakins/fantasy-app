/**
 * Writes the stat/filter catalog the Ask feature sends to the model into the backend eval fixtures,
 * so `pytest -m eval` checks the real ids. Run: npm run export:catalog
 */
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { buildIntentCatalog } from "../src/shared/lib/nlqCatalog";

const target = fileURLToPath(new URL("../../backend/tests/eval/catalog.json", import.meta.url));
writeFileSync(target, `${JSON.stringify(buildIntentCatalog(), null, 2)}\n`);
process.stdout.write(`wrote ${target}\n`);
