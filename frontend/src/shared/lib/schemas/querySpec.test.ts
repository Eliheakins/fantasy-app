import { describe, expect, it } from "vitest";

import { parseQuerySpec } from "./querySpec";

const spec = (overrides: Record<string, unknown> = {}) => ({
  subject: { kind: "players", gsis_ids: ["00-0033873"] },
  metrics: ["pass_yards"],
  filters: ["season-2023"],
  granularity: "total",
  ...overrides,
});

describe("parseQuerySpec", () => {
  it("fills the optional parts with defaults", () => {
    expect(parseQuerySpec(spec())).toMatchObject({ group_by: [], order_by: null, limit: null });
  });

  it("accepts a league leaderboard", () => {
    const parsed = parseQuerySpec(
      spec({
        subject: { kind: "league" },
        order_by: { metric: "pass_yards", direction: "desc" },
        limit: 10,
      }),
    );

    expect(parsed.subject.kind).toBe("league");
  });

  it("requires a league query to have an order and a limit", () => {
    expect(() => parseQuerySpec(spec({ subject: { kind: "league" } }))).toThrow(/league/);
  });

  it("requires order_by to name one of the metrics", () => {
    expect(() =>
      parseQuerySpec(spec({ order_by: { metric: "rec_yards", direction: "desc" } })),
    ).toThrow(/order_by/);
  });

  it("caps the limit and the metric count and rejects repeats", () => {
    expect(() => parseQuerySpec(spec({ limit: 0 }))).toThrow();
    expect(() => parseQuerySpec(spec({ limit: 101 }))).toThrow();
    expect(() => parseQuerySpec(spec({ metrics: [] }))).toThrow();
    expect(() => parseQuerySpec(spec({ metrics: ["a", "b", "c", "d", "e", "f"] }))).toThrow();
    expect(() => parseQuerySpec(spec({ metrics: ["pass_yards", "pass_yards"] }))).toThrow(/repeat/);
  });

  it("needs at least one player or team and a known subject kind", () => {
    expect(() => parseQuerySpec(spec({ subject: { kind: "players", gsis_ids: [] } }))).toThrow();
    expect(() => parseQuerySpec(spec({ subject: { kind: "teams", teams: [] } }))).toThrow();
    expect(() => parseQuerySpec(spec({ subject: { kind: "coaches" } }))).toThrow();
  });

  it("rejects an unknown group_by", () => {
    expect(() => parseQuerySpec(spec({ group_by: ["decade"] }))).toThrow();
  });
});
