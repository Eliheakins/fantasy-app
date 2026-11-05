import { describe, expect, it } from "vitest";

import { buildFilterChipGroups } from "@/stat/config/queryBuilderOptions";
import { getStatById } from "@/stat/config/statDictionary";
import { formatMetricValueHeader } from "@/stat/lib/queryBuilder";

import { ColumnStore, type ColumnLoader, type ColumnSource } from "./columns";
import { type LeaguePointsRow } from "./leaguePointsQuery";
import { runStatQuery, type StatQueryParams } from "./statQuery";

const QB = "00-QB";
const RB = "00-RB";
const FA = "00-FA";

const POINTS: LeaguePointsRow[] = [
  { gsis_id: QB, season: 2023, week: 1, points: 10 },
  { gsis_id: QB, season: 2023, week: 2, points: 20 },
  { gsis_id: QB, season: 2023, week: 3, points: 0 }, // played and scored nothing: still a game
  { gsis_id: RB, season: 2023, week: 1, points: 5 },
  { gsis_id: RB, season: 2023, week: 2, points: 15 },
  { gsis_id: RB, season: 2022, week: 1, points: 100 },
  { gsis_id: FA, season: 2023, week: 1, points: 40 },
];

const store = new ColumnStore(async () => {
  throw new Error("a league-points query must not read any shard");
});
const chipGroups = buildFilterChipGroups([2022, 2023]);

function params(overrides: Partial<StatQueryParams> = {}): StatQueryParams {
  return {
    statIds: ["league_pts"],
    filterChipState: { "season-2023": true, "stype-reg": true },
    gsisIds: null,
    sources: [],
    leaguePoints: POINTS,
    granularity: "total",
    minPlays: 0,
    chipGroups,
    ...overrides,
  };
}

const byPlayer = (rows: Record<string, unknown>[]) => Object.fromEntries(rows.map((r) => [r.player_id, r.m_league_pts]));

describe("league points from the selected league", () => {
  it("is one catalog stat that names its source and carries no play SQL", () => {
    const stat = getStatById("league_pts");
    expect(stat).toMatchObject({ source: "league", base_sql: "", rate_only: false });
  });

  it("totals the weekly points of the season in the chips", async () => {
    const result = await runStatQuery(params(), store);
    expect(byPlayer(result.rows)).toEqual({ [QB]: 30, [RB]: 20, [FA]: 40 });
  });

  it("divides by the games that have a points row for per game", async () => {
    const result = await runStatQuery(params({ granularity: "per_game" }), store);
    expect(byPlayer(result.rows)).toEqual({ [QB]: 10, [RB]: 10, [FA]: 40 });
  });

  it("ranks players by points, best first, and keeps the first rows", async () => {
    const result = await runStatQuery(
      params({ order: { metric: "league_pts", direction: "desc" }, limit: 2 }),
      store,
    );
    expect(result.rows.map((r) => r.player_id)).toEqual([FA, QB]);
  });

  it("answers for the named players and narrows to a player set", async () => {
    const named = await runStatQuery(params({ gsisIds: [RB] }), store);
    expect(byPlayer(named.rows)).toEqual({ [RB]: 20 });
    const free = await runStatQuery(params({ playerSet: { ids: [QB, RB], exclude: true } }), store);
    expect(byPlayer(free.rows)).toEqual({ [FA]: 40 });
  });

  it("splits by week and sums several seasons when more are chosen", async () => {
    const weekly = await runStatQuery(params({ gsisIds: [QB], split: "week" }), store);
    expect(weekly.rows.map((r) => [r.week, r.m_league_pts])).toEqual([
      [1, 10],
      [2, 20],
      [3, 0],
    ]);
    const both = await runStatQuery(
      params({ gsisIds: [RB], filterChipState: { "season-2022": true, "season-2023": true } }),
      store,
    );
    expect(byPlayer(both.rows)).toEqual({ [RB]: 120 });
  });

  it("filters by week like the other counting stats", async () => {
    const late = await runStatQuery(
      params({ gsisIds: [QB], filterChipState: { "season-2023": true, "week-late": true } }),
      store,
    );
    expect(late.rows).toEqual([]);
  });

  it("gives no rows and says so for the playoffs, which the league's points do not cover", async () => {
    const post = await runStatQuery(params({ filterChipState: { "season-2023": true, "stype-post": true } }), store);
    expect(post.rows).toEqual([]);
    expect(post.notices).toEqual(["League points are regular season only."]);
  });

  it("names the selected league in the label, only when a name is given", () => {
    const stat = getStatById("league_pts");
    expect(formatMetricValueHeader(stat, "per_game", "Colgate")).toBe("League points (Colgate) (per game)");
    expect(formatMetricValueHeader(stat, "total")).toBe("League points (total)");
    expect(formatMetricValueHeader(getStatById("pass_yards"), "total", "Colgate")).toBe("Pass yards (total)");
  });

  it("reports per play as per game, the only rate it has", () => {
    const stat = getStatById("league_pts");
    expect(formatMetricValueHeader(stat, "per_play")).toContain("per game");
  });
});

describe("league points and play-level filters", () => {
  it("returns no numbers and a notice naming the filter instead of unfiltered totals", async () => {
    const result = await runStatQuery(
      params({ filterChipState: { "season-2023": true, "down-3": true } }),
      store,
    );
    expect(result.rows).toEqual([]);
    expect(result.notices).toHaveLength(1);
    expect(result.notices![0]).toMatch(/League points/);
    expect(result.notices![0]).toMatch(/Down/);
  });

  it("has no notice when only season, season type and week filters are on", async () => {
    const result = await runStatQuery(params(), store);
    expect(result.notices ?? []).toEqual([]);
  });
});

describe("league points without a league or for teams", () => {
  it("says to pick a league when none is selected", async () => {
    await expect(runStatQuery(params({ leaguePoints: null }), store)).rejects.toThrow(/Pick a league/);
    await expect(runStatQuery(params({ leaguePoints: undefined }), store)).rejects.toThrow(/League points/);
  });

  it("does not offer team rows", async () => {
    await expect(
      runStatQuery(params({ teams: { ids: null, side: "offense" } }), store),
    ).rejects.toThrow(/players, not teams/);
  });
});

describe("league points next to a play stat", () => {
  const TABLE: ColumnSource = { year: 0, url: "mem://player_game" };
  // The quarterback has game rows; the free agent has points but no game rows in the table.
  const GAMES = [
    { gsis_id: QB, season: 2023, week: 1, season_type: "REG", attempts: 30, passing_yards: 300 },
    { gsis_id: QB, season: 2023, week: 2, season_type: "REG", attempts: 20, passing_yards: 200 },
    { gsis_id: RB, season: 2023, week: 1, season_type: "REG", attempts: 0, passing_yards: 0 },
  ];
  const gameStore = new ColumnStore((async (_source: ColumnSource, column: string) =>
    GAMES.map((r) => (r as Record<string, unknown>)[column] ?? null)) as ColumnLoader);
  const mixed = (overrides: Partial<StatQueryParams> = {}) =>
    params({ statIds: ["pass_yards", "league_pts"], playerGame: TABLE, ...overrides });

  it("keeps the play rows as the base, so a player with points but no play rows does not pad the table", async () => {
    const result = await runStatQuery(mixed(), gameStore);
    expect(result.rows).toEqual([{ player_id: QB, m_pass_yards: 500, m_league_pts: 30 }]);
  });

  it("applies the play stat's minimum plays and role to the points too", async () => {
    const result = await runStatQuery(mixed({ minPlays: 100 }), gameStore);
    expect(result.rows).toEqual([]);
  });
});
