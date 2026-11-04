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

  it("runs a league-wide leaderboard", () => {
    const league = {
      ...base,
      subject: { kind: "league" as const },
      order_by: { metric: "pass_yards", direction: "desc" as const },
      limit: 10,
    };

    expect(unsupportedReasons(league)).toEqual([]);
  });

  it("runs ordering and limits on named players", () => {
    const spec = { ...base, order_by: { metric: "pass_yards", direction: "asc" as const }, limit: 5 };

    expect(unsupportedReasons(spec)).toEqual([]);
  });

  it("says team queries are not supported yet", () => {
    const teams = {
      ...base,
      subject: { kind: "teams" as const, teams: ["KC"] },
      order_by: { metric: "pass_yards", direction: "desc" as const },
      limit: 5,
    };

    expect(unsupportedReasons(teams)).toEqual(["Team queries aren't supported yet."]);
  });

  it("says grouping by season or week is not supported yet", () => {
    expect(unsupportedReasons({ ...base, group_by: ["season" as const] })).toEqual([
      "Splitting results by season or week isn't supported yet.",
    ]);
  });
});
