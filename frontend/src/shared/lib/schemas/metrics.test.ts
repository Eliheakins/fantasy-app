import { describe, expect, it } from "vitest";

import { parseMetricsFile } from "./metrics";

const metric = (overrides: Record<string, unknown> = {}) => ({
  id: "pass_yards",
  label: "Pass yards",
  category: "passing",
  player_role: "passer",
  play_type: "pass",
  base_sql: "SUM(yards_gained)",
  rate_only: false,
  aliases: ["passing yards"],
  reference_values: [],
  ...overrides,
});

const file = (...metrics: Record<string, unknown>[]) => ({
  schema_version: 1,
  categories: [{ id: "passing", label: "Passing" }],
  metrics,
});

describe("parseMetricsFile", () => {
  it("accepts a valid file and fills optional fields", () => {
    const parsed = parseMetricsFile(file(metric()));

    expect(parsed.metrics[0]).toMatchObject({ id: "pass_yards", percent_format: false, play_filter: null });
  });

  it("treats a null description or help like a missing one, as the backend does", () => {
    const parsed = parseMetricsFile(file(metric({ description: null, help: null })));

    expect(parsed.metrics[0]!.help).toBeNull();
  });

  it("rejects empty text, duplicate categories and over-long alias lists", () => {
    for (const field of ["label", "base_sql", "play_filter"]) {
      expect(() => parseMetricsFile(file(metric({ [field]: "" })))).toThrow();
    }
    expect(() => parseMetricsFile({ ...file(metric()), categories: [{ id: "passing", label: "A" }, { id: "passing", label: "B" }] })).toThrow(/Duplicate category/);
    expect(() => parseMetricsFile(file(metric({ aliases: Array.from({ length: 21 }, (_, i) => `alias ${i}`) })))).toThrow();
    expect(() => parseMetricsFile(file(metric({ aliases: ["two  spaces"] })))).toThrow(/single spaces/);
  });

  it("rejects duplicate metric ids", () => {
    expect(() => parseMetricsFile(file(metric(), metric({ aliases: ["other"] })))).toThrow(/Duplicate metric id/);
  });

  it("rejects a metric in an undefined category", () => {
    expect(() => parseMetricsFile(file(metric({ category: "kicking" })))).toThrow(/category/);
  });

  it("rejects uppercase aliases", () => {
    expect(() => parseMetricsFile(file(metric({ aliases: ["Passing Yards"] })))).toThrow(/lowercase/);
  });

  it("rejects an alias used by two metrics", () => {
    const other = metric({ id: "pass_tds", label: "Pass TDs", aliases: ["passing yards"] });

    expect(() => parseMetricsFile(file(metric(), other))).toThrow(/passing yards/);
  });

  it("rejects unknown roles and unknown file versions", () => {
    expect(() => parseMetricsFile(file(metric({ player_role: "kicker" })))).toThrow();
    expect(() => parseMetricsFile({ ...file(metric()), schema_version: 2 })).toThrow();
  });

  it("names the file in the error so a bad edit is easy to find", () => {
    expect(() => parseMetricsFile({})).toThrow(/metrics\.json/);
  });
});
