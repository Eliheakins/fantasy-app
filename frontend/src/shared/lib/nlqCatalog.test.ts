import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { buildIntentCatalog } from "./nlqCatalog";

describe("buildIntentCatalog", () => {
  it("lists every stat and filter option once with unique ids", () => {
    const { stats, filters } = buildIntentCatalog();

    expect(stats.length).toBeGreaterThan(0);
    expect(new Set(stats.map((s) => s.id)).size).toBe(stats.length);
    expect(new Set(filters.map((f) => f.id)).size).toBe(filters.length);
    expect(filters.find((f) => f.id === "season-2023")).toEqual({
      id: "season-2023",
      label: "2023",
      group: "Season",
    });
  });

  it("matches the catalog committed for the backend eval (run npm run export:catalog if not)", () => {
    const path = fileURLToPath(
      new URL("../../../../backend/tests/eval/catalog.json", import.meta.url),
    );

    expect(JSON.parse(readFileSync(path, "utf8"))).toEqual(buildIntentCatalog());
  });
});
