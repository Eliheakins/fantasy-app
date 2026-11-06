import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { FIXTURE_SEASONS } from "@/stat/testing/seasons";

import { buildIntentCatalog } from "./nlqCatalog";

describe("buildIntentCatalog", () => {
  it("lists every stat and filter option once with unique ids", () => {
    const { stats, filters } = buildIntentCatalog(FIXTURE_SEASONS);

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
    const { stats } = buildIntentCatalog(FIXTURE_SEASONS);

    expect(stats.find((s) => s.id === "pass_int")?.aliases).toContain("picks");
    expect(stats.filter((s) => s.aliases.length === 0)).toEqual([]);
  });

  it("matches the catalog committed for the backend eval (refresh it with UPDATE_CATALOG=1 npx vitest run nlqCatalog.test.ts)", () => {
    const path = resolve(import.meta.dirname, "../../../../tests/stat/eval/catalog.json");
    if (process.env.UPDATE_CATALOG) {
      writeFileSync(path, `${JSON.stringify(buildIntentCatalog(FIXTURE_SEASONS), null, 2)}\n`);
    }

    expect(JSON.parse(readFileSync(path, "utf8"))).toEqual(buildIntentCatalog(FIXTURE_SEASONS));
  });
});
