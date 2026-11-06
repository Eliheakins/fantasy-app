/**
 * Role-aware efficiency and team stats on a hand-built game. Expected values are worked out by hand
 * from the plays below; the reference-value tests check the same SQL against nflverse totals.
 */
import { describe, expect, it } from "vitest";

import { buildFilterChipGroups } from "@/stat/config/queryBuilderOptions";

import { ColumnStore, type ColumnSource } from "./columns";
import { runStatQuery, type StatQueryParams } from "./statQuery";

const Q = "00-QB";
const R = "00-RB";
const W = "00-WR";
const B = "00-BUF";

type Play = Record<string, unknown>;
const FLAGS = { complete_pass: 0, incomplete_pass: 0, interception: 0, sack: 0 };
const kc = { posteam: "KC", defteam: "BUF" };
const at = { game_id: "g1", season: 2024, season_type: "REG", week: 1, posteam_type: "home" };

const PLAYS: Play[] = [
  { ...at, ...kc, ...FLAGS, play_type: "pass", passer_player_id: Q, receiver_player_id: W, complete_pass: 1, yards_gained: 10, air_yards: 6, epa: 1.0, success: 1 },
  { ...at, ...kc, ...FLAGS, play_type: "pass", passer_player_id: Q, receiver_player_id: W, incomplete_pass: 1, yards_gained: 0, air_yards: 12, epa: -0.5, success: 0 },
  { ...at, ...kc, ...FLAGS, play_type: "pass", passer_player_id: Q, sack: 1, yards_gained: -7, epa: -2.0, success: 0 },
  { ...at, ...kc, ...FLAGS, play_type: "run", rusher_player_id: R, yards_gained: 5, epa: 0.5, success: 1 },
  { ...at, ...kc, ...FLAGS, play_type: "run", rusher_player_id: Q, yards_gained: 8, epa: 1.5, success: 1 },
  { ...at, posteam: "BUF", defteam: "KC", posteam_type: "away", ...FLAGS, play_type: "run", rusher_player_id: B, yards_gained: 2, epa: -0.3, success: 0 },
];

const SOURCE: ColumnSource = { year: 2024, url: "mem://2024" };
const store = new ColumnStore(async (_source, column) => PLAYS.map((p) => p[column] ?? null));

const query = (over: Partial<StatQueryParams>): StatQueryParams => ({
  statIds: ["eff_epa"],
  filterChipState: {},
  gsisIds: null,
  sources: [SOURCE],
  granularity: "per_play",
  minPlays: 0,
  chipGroups: buildFilterChipGroups([2024]),
  ...over,
});

const value = (rows: Record<string, unknown>[], key: string, id: string, stat: string) =>
  rows.find((r) => r[key] === id)?.[`m_${stat}`];

describe("role-aware efficiency", () => {
  it("rates a rusher's EPA over his carries, scrambles included for a quarterback", async () => {
    const { rows } = await runStatQuery(query({ statIds: ["rush_epa", "rush_success"] }), store);

    expect(value(rows, "player_id", R, "rush_epa")).toBeCloseTo(0.5);
    expect(value(rows, "player_id", Q, "rush_epa")).toBeCloseTo(1.5);
    expect(value(rows, "player_id", R, "rush_success")).toBeCloseTo(100);
  });

  it("rates a receiver's EPA and depth over his targets", async () => {
    const { rows } = await runStatQuery(query({ statIds: ["rec_epa", "rec_adot"], gsisIds: [W] }), store);

    expect(value(rows, "player_id", W, "rec_epa")).toBeCloseTo(0.25);
    expect(value(rows, "player_id", W, "rec_adot")).toBeCloseTo(9);
  });

  it("keeps the passer's EPA on dropbacks, sacks included", async () => {
    const { rows } = await runStatQuery(query({ gsisIds: [Q] }), store);

    expect(value(rows, "player_id", Q, "eff_epa")).toBeCloseTo(-0.5);
  });
});

describe("team stats over every play", () => {
  it("averages a team's EPA and success over its pass and run plays", async () => {
    const { rows } = await runStatQuery(
      query({ statIds: ["team_epa", "team_success"], teams: { ids: null, side: "offense" } }),
      store,
    );

    expect(value(rows, "team_id", "KC", "team_epa")).toBeCloseTo(0.1);
    expect(value(rows, "team_id", "KC", "team_success")).toBeCloseTo(60);
    expect(value(rows, "team_id", "BUF", "team_epa")).toBeCloseTo(-0.3);
  });

  it("gives a defense the EPA its opponents gained", async () => {
    const { rows } = await runStatQuery(query({ statIds: ["team_epa"], teams: { ids: ["BUF"], side: "defense" } }), store);

    expect(value(rows, "team_id", "BUF", "team_epa")).toBeCloseTo(0.1);
  });

  it("refuses a team-only stat for players", async () => {
    await expect(runStatQuery(query({ statIds: ["team_epa"], gsisIds: [Q] }), store)).rejects.toThrow(/team stat/);
  });
});
