/** Week chips and "last N games" on hand-built games: a receiver with one catch a week, weeks 1 to 4. */
import { describe, expect, it } from "vitest";

import { buildFilterChipGroups } from "@/stat/config/queryBuilderOptions";

import { ColumnStore, type ColumnSource } from "./columns";
import { runStatQuery, type StatQueryParams } from "./statQuery";

const W = "00-WR";
// Week w: one catch of 10 * w yards; week 3 also a carry of 5 yards.
const PLAYS = [1, 2, 3, 4].flatMap((w) => [
  {
    game_id: `g${w}`,
    season: 2026,
    season_type: "REG",
    week: w,
    posteam: "KC",
    play_type: "pass",
    receiver_player_id: W,
    complete_pass: 1,
    yards_gained: 10 * w,
  },
  ...(w === 3
    ? [{ game_id: "g3", season: 2026, season_type: "REG", week: 3, posteam: "KC", play_type: "run", rusher_player_id: W, yards_gained: 5 }]
    : []),
]);
const GAMES = [1, 2, 3, 4].map((w) => ({ gsis_id: W, season: 2026, season_type: "REG", week: w, receiving_yards: 10 * w, targets: 1 }));
const PBP: ColumnSource = { year: 2026, url: "mem://pbp" };
const TABLE: ColumnSource = { year: 0, url: "mem://player_game" };
const store = new ColumnStore(async (source, column) =>
  (source.url === TABLE.url ? GAMES : PLAYS).map((r) => (r as Record<string, unknown>)[column] ?? null),
);

const query = (over: Partial<StatQueryParams>): StatQueryParams => ({
  statIds: ["rec_yards"],
  filterChipState: { "season-2026": true },
  gsisIds: [W],
  sources: [PBP],
  granularity: "total",
  minPlays: 0,
  chipGroups: buildFilterChipGroups([2026]),
  ...over,
});
const yards = async (over: Partial<StatQueryParams>) => (await runStatQuery(query(over), store)).rows[0]?.m_rec_yards;

describe("weeks and last N games", () => {
  it("keeps only the week chips that are on", async () => {
    expect(await yards({ filterChipState: { "season-2026": true, "wk-2": true, "wk-3": true } })).toBe(50);
  });

  it("keeps a player's latest N games, from the play-by-play", async () => {
    expect(await yards({ lastGames: 2 })).toBe(70);
    expect(await yards({ lastGames: 2, granularity: "per_game" })).toBe(35);
  });

  it("counts a game with only a carry as one of the player's games", async () => {
    // Weeks 3 and 4 are the latest two; week 3 has the catch and the carry.
    expect(await yards({ lastGames: 2, filterChipState: { "season-2026": true, "wk-1": true, "wk-2": true, "wk-3": true } })).toBe(50);
  });

  it("keeps a player's latest N games, from the player-game table", async () => {
    expect(await yards({ lastGames: 3, playerGame: TABLE })).toBe(90);
  });
});
