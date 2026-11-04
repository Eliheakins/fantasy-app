import { describe, expect, it } from "vitest";

import { buildFilterChipGroups } from "@/shared/config/queryBuilderOptions";

import { ColumnStore, type ColumnLoader, type ColumnSource } from "./columns";
import { canServeFromPlayerGame, runPlayerGameQuery } from "./playerGameQuery";
import type { StatQueryParams } from "./statQuery";

const QB = "00-QB";
const RB = "00-RB";
const TABLE: ColumnSource = { year: 0, url: "mem://player_game" };

interface Row {
  gsis_id: string;
  season: number;
  week: number;
  season_type: string;
  attempts?: number;
  carries?: number;
  targets?: number;
  passing_yards?: number;
  passing_tds?: number;
  rushing_yards?: number;
  rushing_tds?: number;
  receptions?: number;
  receiving_yards?: number;
  receiving_yards_after_catch?: number;
}

const ROWS: Row[] = [
  { gsis_id: QB, season: 2023, week: 1, season_type: "REG", attempts: 30, passing_yards: 300, passing_tds: 2 },
  { gsis_id: QB, season: 2023, week: 2, season_type: "REG", attempts: 20, passing_yards: 200, passing_tds: 1 },
  { gsis_id: QB, season: 2023, week: 3, season_type: "POST", attempts: 40, passing_yards: 400, passing_tds: 3 },
  { gsis_id: QB, season: 2022, week: 1, season_type: "REG", attempts: 10, passing_yards: 50, passing_tds: 0 },
  { gsis_id: RB, season: 2023, week: 1, season_type: "REG", carries: 20, rushing_yards: 100, rushing_tds: 1 },
  { gsis_id: RB, season: 2023, week: 2, season_type: "REG", carries: 0, targets: 4, receptions: 3, receiving_yards: 30 },
];

/** Records every read, so a test can see which file and columns a query touched. */
function memoryStore() {
  const reads: { url: string; column: string }[] = [];
  const loader: ColumnLoader = async (source, column) => {
    reads.push({ url: source.url, column });
    return ROWS.map((r) => (r as unknown as Record<string, unknown>)[column] ?? null);
  };
  return { store: new ColumnStore(loader), reads };
}

const chipGroups = buildFilterChipGroups([2022, 2023]);

function params(overrides: Partial<StatQueryParams> = {}): StatQueryParams {
  return {
    statIds: ["pass_yards"],
    filterChipState: { "season-2023": true, "stype-reg": true },
    gsisIds: [QB],
    sources: [],
    playerGame: TABLE,
    granularity: "total",
    minPlays: 0,
    chipGroups,
    ...overrides,
  };
}

const firstOption = (groupId: string) => chipGroups.find((g) => g.id === groupId)!.options[0]!.id;

describe("canServeFromPlayerGame", () => {
  it("accepts counting stats with only season, season type and week filters", () => {
    expect(canServeFromPlayerGame(params())).toBe(true);
    expect(canServeFromPlayerGame(params({ granularity: "per_game" }))).toBe(true);
  });

  it("is false without a player-game table", () => {
    expect(canServeFromPlayerGame(params({ playerGame: null }))).toBe(false);
  });

  it("is false for a situational filter, which only the plays can answer", () => {
    expect(canServeFromPlayerGame(params({ filterChipState: { "down-3": true } }))).toBe(false);
    expect(canServeFromPlayerGame(params({ filterChipState: { [firstOption("location")]: true } }))).toBe(false);
  });

  it("ignores a chip that is switched off", () => {
    expect(canServeFromPlayerGame(params({ filterChipState: { "down-3": false, "season-2023": true } }))).toBe(true);
  });

  it("is false for a rate stat or a stat without a tier-1 column", () => {
    expect(canServeFromPlayerGame(params({ statIds: ["cmp_pct"] }))).toBe(false);
    expect(canServeFromPlayerGame(params({ statIds: ["pass_yards", "eff_wpa"] }))).toBe(false);
  });

  it("accepts per play, which divides by the role's attempts, carries or targets", () => {
    expect(canServeFromPlayerGame(params({ granularity: "per_play" }))).toBe(true);
  });

  it("is false when no stat is selected", () => {
    expect(canServeFromPlayerGame(params({ statIds: [] }))).toBe(false);
  });
});

describe("runPlayerGameQuery", () => {
  it("totals a stat over the chosen season and season type", async () => {
    const { store } = memoryStore();

    const result = await runPlayerGameQuery(params(), TABLE, store);

    expect(result.rows).toEqual([{ player_id: QB, m_pass_yards: 500 }]);
  });

  it("includes every season and season type when no chip narrows them", async () => {
    const { store } = memoryStore();

    const result = await runPlayerGameQuery(params({ filterChipState: {} }), TABLE, store);

    expect(result.rows[0]?.m_pass_yards).toBe(950);
  });

  it("divides by the games where the player had a pass attempt for per game", async () => {
    const { store } = memoryStore();

    const result = await runPlayerGameQuery(params({ granularity: "per_game" }), TABLE, store);

    expect(result.rows[0]?.m_pass_yards).toBe(250);
  });

  it("divides by the player's attempts for per play", async () => {
    const { store } = memoryStore();

    const result = await runPlayerGameQuery(params({ granularity: "per_play" }), TABLE, store);

    expect(result.rows[0]?.m_pass_yards).toBe(10);
  });

  it("drops a player whose volume is under the minimum plays", async () => {
    const { store } = memoryStore();

    const result = await runPlayerGameQuery(params({ minPlays: 60 }), TABLE, store);

    expect(result.rows).toEqual([]);
  });

  it("measures a back's volume in carries and a receiver's in targets", async () => {
    const { store } = memoryStore();

    const rush = await runPlayerGameQuery(
      params({ statIds: ["rush_yards"], gsisIds: [RB], minPlays: 20 }),
      TABLE,
      store,
    );
    const rec = await runPlayerGameQuery(
      params({ statIds: ["rec_yards"], gsisIds: [RB], minPlays: 5 }),
      TABLE,
      store,
    );

    expect(rush.rows[0]?.m_rush_yards).toBe(100);
    expect(rec.rows).toEqual([]);
  });

  it("returns a row only for players it was asked about", async () => {
    const { store } = memoryStore();

    const result = await runPlayerGameQuery(params({ gsisIds: ["00-NOBODY"] }), TABLE, store);

    expect(result.rows).toEqual([]);
  });

  it("returns no rows, not an error, when the chips match no data", async () => {
    const { store } = memoryStore();

    const result = await runPlayerGameQuery(
      params({ filterChipState: { "season-2022": true, "stype-post": true } }),
      TABLE,
      store,
    );

    expect(result.rows).toEqual([]);
  });

  it("reads only the player-game file and only the columns the stat needs", async () => {
    const { store, reads } = memoryStore();

    await runPlayerGameQuery(params(), TABLE, store);

    expect(new Set(reads.map((r) => r.url))).toEqual(new Set([TABLE.url]));
    expect(reads.map((r) => r.column).sort()).toEqual(
      ["attempts", "gsis_id", "passing_yards", "season", "season_type"].sort(),
    );
  });

  it("merges stats of different roles into one row per player", async () => {
    const { store } = memoryStore();

    const result = await runPlayerGameQuery(
      params({ statIds: ["rush_yards", "rec_yards"], gsisIds: [RB], filterChipState: {} }),
      TABLE,
      store,
    );

    expect(result.rows).toEqual([{ player_id: RB, m_rush_yards: 100, m_rec_yards: 30 }]);
  });
});
