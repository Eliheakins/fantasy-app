import { describe, expect, it } from "vitest";

import { buildFilterChipGroups } from "@/stat/config/queryBuilderOptions";

import { ColumnStore, type ColumnSource } from "./columns";
import { narrowPlayerSet } from "./playerFilters";
import { runStatQuery, type StatQueryParams } from "./statQuery";

// Three receivers: a veteran WR, a WR drafted in 2025 and a TE drafted in 2025 (index seen in 2026).
const INDEX = [
  { gsis_id: "VET", position: "WR", season: 2026, years_exp: 6 },
  { gsis_id: "ROOK", position: "WR", season: 2026, years_exp: 1 },
  { gsis_id: "TE1", position: "TE", season: 2026, years_exp: 1 },
];
const PLAYS = ["VET", "ROOK", "TE1"].map((id, k) => ({
  game_id: "g1",
  season: 2025,
  season_type: "REG",
  week: 1,
  posteam: "KC",
  play_type: "pass",
  receiver_player_id: id,
  yards_gained: 10 * (k + 1),
}));
const SHARD: ColumnSource = { year: 2025, url: "mem://2025" };
const INDEX_SOURCE: ColumnSource = { year: 0, url: "mem://index" };
const store = new ColumnStore(async (source, column) =>
  (source.url === INDEX_SOURCE.url ? INDEX : PLAYS).map((r) => (r as Record<string, unknown>)[column] ?? null),
);
const ids = async (over: Partial<StatQueryParams>) =>
  (
    await runStatQuery(
      {
        statIds: ["rec_yards"],
        filterChipState: { "season-2025": true },
        gsisIds: null,
        sources: [SHARD],
        playerIndex: INDEX_SOURCE,
        granularity: "total",
        minPlays: 0,
        chipGroups: buildFilterChipGroups([2025]),
        ...over,
      },
      store,
    )
  ).rows.map((r) => r.player_id);

describe("position and rookie filters", () => {
  it("keeps one position", async () => {
    expect(await ids({ position: "WR" })).toEqual(["ROOK", "VET"]);
  });

  it("keeps the players whose first season is the one asked about", async () => {
    expect(await ids({ rookie: true })).toEqual(["TE1", "ROOK"]);
    expect(await ids({ rookie: true, position: "WR" })).toEqual(["ROOK"]);
  });

  it("narrows a league's player set rather than replacing it", () => {
    expect(narrowPlayerSet({ ids: ["VET"], exclude: true }, new Set(["VET", "ROOK"]))).toEqual({ ids: ["ROOK"], exclude: false });
    expect(narrowPlayerSet({ ids: ["VET"], exclude: false }, new Set(["VET", "ROOK"]))).toEqual({ ids: ["VET"], exclude: false });
  });
});
