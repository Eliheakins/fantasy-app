/**
 * Derived stats on hand-built games, every expected value worked out by hand. W is traded: he plays
 * g1 for KC and g2 for BUF, so his team totals come from KC's g1 and BUF's g2 only (not KC's g3).
 */
import { describe, expect, it } from "vitest";

import { buildFilterChipGroups } from "@/stat/config/queryBuilderOptions";

import { ColumnStore, type ColumnSource } from "./columns";
import { runStatQuery, type StatQueryParams } from "./statQuery";

const W = "00-W";
const X = "00-X";
const Y = "00-Y";
const R = "00-R";
const FLAGS = { complete_pass: 0, incomplete_pass: 0, interception: 0, sack: 0, pass_touchdown: 0, rush_touchdown: 0, fumble_lost: 0 };
const game = (id: string, week: number, team: string) => ({
  game_id: id,
  season: 2024,
  season_type: "REG",
  week,
  posteam: team,
  defteam: team === "KC" ? "BUF" : "KC",
});
const pass = (g: object, passer: string, receiver: string | null, air: number, yards: number, extra: object = {}) => ({
  ...g,
  ...FLAGS,
  play_type: "pass",
  passer_player_id: passer,
  receiver_player_id: receiver,
  air_yards: air,
  yards_gained: yards,
  ...(yards > 0 ? { complete_pass: 1 } : { incomplete_pass: 1 }),
  ...extra,
});
const run = (g: object, rusher: string, yards: number, extra: object = {}) => ({
  ...g,
  ...FLAGS,
  play_type: "run",
  rusher_player_id: rusher,
  yards_gained: yards,
  ...extra,
});

const g1 = game("g1", 1, "KC");
const g2 = game("g2", 2, "BUF");
const g3 = game("g3", 3, "KC");
const PLAYS: Record<string, unknown>[] = [
  pass(g1, "QK", W, 10, 15),
  pass(g1, "QK", X, 20, 0),
  pass(g1, "QK", W, 5, 5, { pass_touchdown: 1 }),
  pass(g1, "QK", null, 8, 0), // thrown away: an attempt with air yards and no target
  run(g1, R, 4),
  run(g1, R, 6, { rush_touchdown: 1 }),
  pass(g2, "QB", W, 30, 30),
  pass(g2, "QB", Y, 10, 0),
  pass(g3, "QK", X, 12, 12),
];

const SOURCE: ColumnSource = { year: 2024, url: "mem://2024" };
const store = new ColumnStore(async (_s, column) => PLAYS.map((p) => p[column] ?? null));
const query = (over: Partial<StatQueryParams>): StatQueryParams => ({
  statIds: ["tgt_share"],
  filterChipState: { "season-2024": true },
  gsisIds: null,
  sources: [SOURCE],
  granularity: "total",
  minPlays: 0,
  chipGroups: buildFilterChipGroups([2024]),
  ...over,
});
const valueOf = async (stat: string, id: string, over: Partial<StatQueryParams> = {}) =>
  (await runStatQuery(query({ statIds: [stat], ...over }), store)).rows.find((r) => r.player_id === id)?.[`m_${stat}`];

describe("shares against the player's own team in his own games", () => {
  it("divides targets by his team's targets in the games he played", async () => {
    expect(await valueOf("tgt_share", W)).toBeCloseTo(60); // 3 / (3 KC in g1 + 2 BUF in g2)
  });

  it("divides air yards by every attempt's air yards, throwaways included", async () => {
    expect(await valueOf("air_share", W)).toBeCloseTo((45 / 83) * 100); // KC g1 43 + BUF g2 40
  });

  it("weights the two shares into WOPR", async () => {
    expect(await valueOf("wopr", W)).toBeCloseTo(1.5 * 0.6 + 0.7 * (45 / 83));
  });

  it("gives a back his share of carries and targets", async () => {
    expect(await valueOf("opp_share", R)).toBeCloseTo(40); // 2 carries / (2 carries + 3 targets) in g1
  });

  it("drops a player below the minimum on the share's own volume", async () => {
    const rows = (await runStatQuery(query({ minPlays: 3 }), store)).rows;

    expect(rows.map((r) => r.player_id)).toEqual([W]);
  });
});

describe("totals across roles", () => {
  it("adds rushing and receiving into scrimmage yards, touches and touchdowns", async () => {
    expect(await valueOf("scrim_yds", W)).toBe(50);
    expect(await valueOf("scrim_yds", R)).toBe(10);
    expect(await valueOf("touches", R)).toBe(2);
    expect(await valueOf("yds_per_touch", R)).toBe(5);
    expect(await valueOf("total_tds", W)).toBe(1);
    expect(await valueOf("total_tds", R)).toBe(1);
  });

  it("divides a cross-role total by the games played, per game", async () => {
    expect(await valueOf("scrim_yds", W, { granularity: "per_game" })).toBe(25);
  });

  it("scores standard, half and full PPR", async () => {
    // 50 receiving yards (5), one touchdown (6), three catches.
    expect(await valueOf("fp_std", W)).toBeCloseTo(11);
    expect(await valueOf("fp_half", W)).toBeCloseTo(12.5);
    expect(await valueOf("fp_ppr", W)).toBeCloseTo(14);
  });

  it("converts air yards to receiving yards in RACR", async () => {
    expect(await valueOf("racr", W)).toBeCloseTo(50 / 45);
  });

  it("refuses a share for a team", async () => {
    await expect(runStatQuery(query({ teams: { ids: null, side: "offense" } }), store)).rejects.toThrow(/team has none/);
  });
});
