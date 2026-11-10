import { describe, expect, it } from "vitest";

import { EMPTY_QUERY } from "@/stat/lib/queryUrl";

import { defaultQuery, isBlankQuery } from "./defaultQuery";

describe("defaultQuery", () => {
  it("ranks the latest season's receivers by targets per game", () => {
    const q = defaultQuery(2026);

    expect(q).toMatchObject({ stats: ["rec_tgt"], granularity: "per_game", position: "WR", limit: 25 });
    expect(q.filters).toEqual(["season-2026", "stype-reg"]);
    expect(isBlankQuery(q)).toBe(false);
  });

  it("treats an empty query as blank", () => {
    expect(isBlankQuery(EMPTY_QUERY)).toBe(true);
    expect(isBlankQuery({ ...EMPTY_QUERY, players: ["00-1"] })).toBe(false);
  });
});
