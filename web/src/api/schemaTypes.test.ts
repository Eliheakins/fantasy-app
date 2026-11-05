import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import openapiTS, { COMMENT_HEADER, astToString } from "openapi-typescript";
import { expect, it } from "vitest";

const webRoot = resolve(__dirname, "../..");

// Same generator as `npm run types`, in memory: fails on drift, never rewrites the file.
it("schema.d.ts matches openapi.json (stale? regenerate with `cd web && npm run types`)", async () => {
  const ast = await openapiTS(pathToFileURL(resolve(webRoot, "openapi.json")));
  const committed = readFileSync(resolve(webRoot, "src/api/schema.d.ts"), "utf8");
  expect(COMMENT_HEADER + astToString(ast)).toBe(committed);
}, 15_000);
