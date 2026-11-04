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

  it("gives the model each stat's aliases so it can match how people phrase things", () => {
    const { stats } = buildIntentCatalog();

    expect(stats.find((s) => s.id === "int_rate")?.aliases).toContain("picks");
    expect(stats.filter((s) => s.aliases.length === 0)).toEqual([]);
  });

  it("matches the catalog committed for the backend eval (run npm run export:catalog if not)", () => {
    const path = fileURLToPath(
      new URL("../../../../backend/tests/eval/catalog.json", import.meta.url),
    );

    expect(JSON.parse(readFileSync(path, "utf8"))).toEqual(buildIntentCatalog());
  });
});
