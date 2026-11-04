import { describe, expect, it } from "vitest";

import { specFromIntent, unsupportedReasons } from "./querySpec";
import { parseQuerySpec } from "./schemas/querySpec";

const intent = {
  stat_ids: ["pass_yards"],
  filter_ids: ["season-2023"],
  granularity: "total" as const,
};

describe("specFromIntent", () => {
  it("turns an intent and its resolved players into a players spec", () => {
    const spec = specFromIntent(intent, ["00-0033873", "00-0034857"]);

    expect(spec).toEqual({
      subject: { kind: "players", gsis_ids: ["00-0033873", "00-0034857"] },
      metrics: ["pass_yards"],
      filters: ["season-2023"],
      granularity: "total",
      group_by: [],
      order_by: null,
      limit: null,
    });
  });

  it("produces a spec the schema accepts", () => {
    expect(() => parseQuerySpec(specFromIntent(intent, ["00-0033873"]))).not.toThrow();
  });
});

describe("unsupportedReasons", () => {
  const base = specFromIntent(intent, ["00-0033873"]);

  it("is empty for a spec the engine can run", () => {
    expect(unsupportedReasons(base)).toEqual([]);
  });

  it("says league-wide leaderboards are not supported yet", () => {
    const league = {
      ...base,
      subject: { kind: "league" as const },
      order_by: { metric: "pass_yards", direction: "desc" as const },
      limit: 10,
    };

    expect(unsupportedReasons(league)).toEqual([
      "League-wide leaderboards and team queries aren't supported yet.",
    ]);
  });

  it("flags grouping, ordering and limits separately", () => {
    const spec = {
      ...base,
      group_by: ["season" as const],
      order_by: { metric: "pass_yards", direction: "asc" as const },
      limit: 5,
    };

    expect(unsupportedReasons(spec)).toEqual([
      "Splitting results by season or week isn't supported yet.",
      "Custom ordering and limits aren't supported yet.",
    ]);
  });
});
