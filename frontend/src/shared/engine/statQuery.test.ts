import { describe, expect, it } from "vitest";

import { buildFilterChipGroups } from "@/shared/config/queryBuilderOptions";

import { ColumnStore, type ColumnLoader, type ColumnSource } from "./columns";
import { runStatQuery, type StatQueryParams } from "./statQuery";

const Q1 = "00-Q1";
const Q2 = "00-Q2";
const R1 = "00-R1";

const COLUMNS = [
  "game_id",
  "season",
  "season_type",
  "week",
  "posteam_type",
  "play_type",
  "down",
  "passer_player_id",
  "rusher_player_id",
  "receiver_player_id",
  "yards_gained",
  "complete_pass",
  "incomplete_pass",
  "interception",
  "sack",
  "pass_touchdown",
] as const;

type Play = Partial<Record<(typeof COLUMNS)[number], unknown>>;

const NOT_A_FLAG = { complete_pass: 0, incomplete_pass: 0, interception: 0, sack: 0 };

function shard(plays: Play[]): Record<string, unknown[]> {
  return Object.fromEntries(COLUMNS.map((c) => [c, plays.map((p) => p[c] ?? null)]));
}

const pass = (p: Play): Play => ({ play_type: "pass", ...NOT_A_FLAG, pass_touchdown: 0, ...p });

const S22: ColumnSource = { year: 2022, url: "mem://2022" };
const S23: ColumnSource = { year: 2023, url: "mem://2023" };

const game = (id: string, week: number, side: string, season = 2023, type = "REG") => ({
  game_id: id,
  season,
  season_type: type,
  week,
  posteam_type: side,
});

const FILES: Record<string, Record<string, unknown[]>> = {
  "mem://2023": shard([
    // g1, week 1, home: a completion, an incompletion, a sack, a penalty row (no outcome flag)
    pass({ ...game("g1", 1, "home"), passer_player_id: Q1, down: 1, complete_pass: 1, yards_gained: 10 }),
    pass({ ...game("g1", 1, "home"), passer_player_id: Q1, down: 2, incomplete_pass: 1, yards_gained: 0 }),
    pass({ ...game("g1", 1, "home"), passer_player_id: Q1, down: 2, sack: 1, yards_gained: -7 }),
    pass({ ...game("g1", 1, "home"), passer_player_id: Q1, down: 2, yards_gained: 15 }),
    pass({ ...game("g1", 1, "home"), passer_player_id: Q2, down: 1, complete_pass: 1, yards_gained: 100 }),
    // g2, week 2, away
    pass({ ...game("g2", 2, "away"), passer_player_id: Q1, down: 3, complete_pass: 1, yards_gained: 20, pass_touchdown: 1 }),
    pass({ ...game("g2", 2, "away"), passer_player_id: Q1, down: 1, interception: 1, yards_gained: 0 }),
    // g5, playoffs
    pass({ ...game("g5", 19, "home", 2023, "POST"), passer_player_id: Q1, down: 1, complete_pass: 1, yards_gained: 5 }),
    // runs
    { ...game("g1", 1, "home"), play_type: "run", rusher_player_id: R1, down: 1, yards_gained: 5, ...NOT_A_FLAG },
    { ...game("g2", 2, "away"), play_type: "run", rusher_player_id: R1, down: 2, yards_gained: 7, ...NOT_A_FLAG },
  ]),
  "mem://2022": shard([
    pass({ ...game("g3", 3, "home", 2022), passer_player_id: Q1, down: 1, complete_pass: 1, yards_gained: 30 }),
  ]),
};

function store() {
  const calls: string[] = [];
  const load: ColumnLoader = async (source, column) => {
    calls.push(`${source.year}:${column}`);
    const values = FILES[source.url]?.[column];
    if (!values) {
      throw new Error(`fixture has no column ${column}`);
    }
    return values;
  };
  return { store: new ColumnStore(load), calls };
}

const base = (over: Partial<StatQueryParams>): StatQueryParams => ({
  statIds: ["pass_yards"],
  filterChipState: { "season-2023": true, "stype-reg": true },
  gsisIds: [Q1],
  sources: [S22, S23],
  granularity: "total",
  minPlays: 0,
  chipGroups: buildFilterChipGroups([2022, 2023]),
  ...over,
});

const valueOf = (result: { rows: Record<string, unknown>[] }, id: string, stat: string) =>
  result.rows.find((r) => r.player_id === id)?.[`m_${stat}`];

describe("runStatQuery counting rules", () => {
  it("leaves sack, penalty and no-play rows out of passing yards", async () => {
    const { store: s } = store();

    const result = await runStatQuery(base({}), s);

    // completion 10 + incompletion 0 + touchdown pass 20 + interception 0; the sack (-7) and penalty (15) are not attempts
    expect(valueOf(result, Q1, "pass_yards")).toBe(30);
  });

  it("counts sacks as dropbacks in sack rate", async () => {
    const { store: s } = store();

    const result = await runStatQuery(base({ statIds: ["pass_sack_rate"] }), s);

    expect(valueOf(result, Q1, "pass_sack_rate")).toBeCloseTo((1 / 6) * 100);
  });

  it("returns one merged row per player with a column per stat, in the order asked", async () => {
    const { store: s } = store();

    const result = await runStatQuery(base({ statIds: ["pass_yards", "pass_sack_rate"] }), s);

    expect(result.columns).toEqual(["player_id", "m_pass_yards", "m_pass_sack_rate"]);
    expect(result.rows).toHaveLength(1);
    expect(result.rows[0]).toMatchObject({ player_id: Q1, m_pass_yards: 30 });
  });

  it("only includes the players asked for, and sorts by the first stat", async () => {
    const { store: s } = store();

    const both = await runStatQuery(base({ gsisIds: [Q1, Q2] }), s);
    const only = await runStatQuery(base({ gsisIds: [Q2] }), s);

    expect(both.rows.map((r) => r.player_id)).toEqual([Q2, Q1]);
    expect(only.rows).toEqual([{ player_id: Q2, m_pass_yards: 100 }]);
  });

  it("uses the rusher and run plays for rushing stats", async () => {
    const { store: s } = store();

    const result = await runStatQuery(base({ statIds: ["rush_yards"], gsisIds: [R1] }), s);

    expect(valueOf(result, R1, "rush_yards")).toBe(12);
  });

  it("sums to a total across seasons when no season chip is on", async () => {
    const { store: s } = store();

    const result = await runStatQuery(base({ filterChipState: { "stype-reg": true } }), s);

    expect(valueOf(result, Q1, "pass_yards")).toBe(60);
  });
});

describe("runStatQuery per game", () => {
  it("divides by the games played in the same season and season type, not career games", async () => {
    const { store: s } = store();

    const result = await runStatQuery(base({ granularity: "per_game" }), s);

    // 30 yards over g1 and g2. The old SQL divided by every game in every mounted season (g1, g2, g5, g3).
    expect(valueOf(result, Q1, "pass_yards")).toBe(15);
  });

  it("does not shrink the game count when a situational filter leaves some games without a matching play", async () => {
    const { store: s } = store();

    const result = await runStatQuery(
      base({ granularity: "per_game", filterChipState: { "season-2023": true, "stype-reg": true, "down-3": true } }),
      s,
    );

    // one third-down attempt for 20 yards; Q1 played two games
    expect(valueOf(result, Q1, "pass_yards")).toBe(10);
  });

  it("divides a rusher's yards by the distinct games they appeared in", async () => {
    const { store: s } = store();

    const result = await runStatQuery(base({ granularity: "per_game", statIds: ["rush_yards"], gsisIds: [R1] }), s);

    expect(valueOf(result, R1, "rush_yards")).toBe(6);
  });

  it("gives per play for a SUM stat as the mean per row", async () => {
    const { store: s } = store();

    const result = await runStatQuery(base({ granularity: "per_play" }), s);

    expect(valueOf(result, Q1, "pass_yards")).toBe(30 / 4);
  });

  it("leaves rate stats as they are whatever granularity is asked", async () => {
    const { store: s } = store();

    const total = await runStatQuery(base({ statIds: ["pass_sack_rate"] }), s);
    const perGame = await runStatQuery(base({ statIds: ["pass_sack_rate"], granularity: "per_game" }), s);

    expect(valueOf(perGame, Q1, "pass_sack_rate")).toBe(valueOf(total, Q1, "pass_sack_rate"));
  });
});

describe("runStatQuery filters and thresholds", () => {
  it("applies situational chips to the rows", async () => {
    const { store: s } = store();

    const result = await runStatQuery(
      base({ filterChipState: { "season-2023": true, "stype-reg": true, "down-3": true } }),
      s,
    );

    expect(valueOf(result, Q1, "pass_yards")).toBe(20);
  });

  it("loads only the seasons the season chips select", async () => {
    const { store: s, calls } = store();

    const result = await runStatQuery(base({ filterChipState: { "season-2022": true } }), s);

    expect(valueOf(result, Q1, "pass_yards")).toBe(30);
    expect(new Set(calls.map((c) => c.split(":")[0]))).toEqual(new Set(["2022"]));
  });

  it("loads only the columns the query needs", async () => {
    const { store: s, calls } = store();

    await runStatQuery(base({}), s);

    const loaded = new Set(calls.map((c) => c.split(":")[1]));
    expect(loaded).not.toContain("pass_touchdown");
    expect(loaded).toContain("yards_gained");
    expect(loaded).toContain("passer_player_id");
  });

  it("drops a player below the minimum plays only from the stats whose rows are too few", async () => {
    const { store: s } = store();

    // 4 attempts but 6 dropbacks for Q1 in 2023 REG
    const result = await runStatQuery(base({ statIds: ["pass_yards", "pass_sack_rate"], minPlays: 5 }), s);

    expect(valueOf(result, Q1, "pass_yards")).toBeNull();
    expect(valueOf(result, Q1, "pass_sack_rate")).not.toBeNull();
  });
});

describe("runStatQuery errors and cancellation", () => {
  it("asks for at least one known stat", async () => {
    const { store: s } = store();

    await expect(runStatQuery(base({ statIds: [] }), s)).rejects.toThrow("Select at least one stat.");
    await expect(runStatQuery(base({ statIds: ["not_a_stat"] }), s)).rejects.toThrow("Select at least one stat.");
  });

  it("rejects when the signal is aborted before the data arrives", async () => {
    const { store: s } = store();
    const controller = new AbortController();
    controller.abort();

    await expect(runStatQuery(base({}), s, controller.signal)).rejects.toThrow();
  });

  it("surfaces a failed data load", async () => {
    const failing = new ColumnStore(async () => {
      throw new Error("network down");
    });

    await expect(runStatQuery(base({}), failing)).rejects.toThrow("network down");
  });
});

describe("league queries, ordering and limits", () => {
  const league = (over: Partial<StatQueryParams> = {}) => base({ gsisIds: null, ...over });
  const ids = (result: { rows: Record<string, unknown>[] }) => result.rows.map((r) => r.player_id);

  it("covers every player in the stat's role when no players are named", async () => {
    const { store: s } = store();

    const result = await runStatQuery(league(), s);

    expect(new Set(ids(result))).toEqual(new Set([Q1, Q2]));
    expect(valueOf(result, Q2, "pass_yards")).toBe(100);
  });

  it("sorts by the ordering stat, highest first by default", async () => {
    const { store: s } = store();

    const result = await runStatQuery(league({ order: { metric: "pass_yards", direction: "desc" } }), s);

    expect(ids(result)).toEqual([Q2, Q1]);
  });

  it("sorts lowest first when asked", async () => {
    const { store: s } = store();

    const result = await runStatQuery(league({ order: { metric: "pass_yards", direction: "asc" } }), s);

    expect(ids(result)).toEqual([Q1, Q2]);
  });

  it("keeps only the first rows after sorting", async () => {
    const { store: s } = store();

    const result = await runStatQuery(league({ order: { metric: "pass_yards", direction: "desc" }, limit: 1 }), s);

    expect(ids(result)).toEqual([Q2]);
  });

  it("applies the minimum plays to the whole league", async () => {
    const { store: s } = store();

    const result = await runStatQuery(league({ minPlays: 2 }), s);

    expect(ids(result)).toEqual([Q1]);
  });

  it("limits a query with named players too", async () => {
    const { store: s } = store();

    const result = await runStatQuery(
      base({ gsisIds: [Q1, Q2], order: { metric: "pass_yards", direction: "desc" }, limit: 1 }),
      s,
    );

    expect(ids(result)).toEqual([Q2]);
  });

  it("puts a player with no value last whichever way it sorts", async () => {
    const { store: s } = store();

    const result = await runStatQuery(
      league({ statIds: ["pass_yards", "pass_sack_rate"], order: { metric: "pass_sack_rate", direction: "desc" } }),
      s,
    );

    expect(ids(result)[0]).toBe(Q1);
  });
});
