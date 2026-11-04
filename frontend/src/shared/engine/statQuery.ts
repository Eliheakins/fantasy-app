import type { FilterChipGroup } from "@/shared/config/queryBuilderOptions";
import { getStatById, playerColumnForRole, type StatDefinition } from "@/shared/config/statDictionary";
import {
  buildFilterWhereSql,
  effectiveGranularity,
  groupStatsByRows,
  mergeStatQueryResults,
  metricSelectAlias,
  splitColumns,
  splitKeyer,
  splitValues,
} from "@/shared/lib/queryBuilder";
import type { QueryOrder } from "@/shared/lib/queryUrl";
import type { GranularityMode, Side, Split } from "@/shared/types/queryBuilder";
import type { QueryResult } from "@/shared/types/workbench";

import type { ColumnSource, ColumnStore } from "./columns";
import { canServeFromPlayerGame, runPlayerGameQuery, wantedPlayers } from "./playerGameQuery";
import {
  columnsIn,
  compileAggregateExpression,
  compileRowExpression,
  parseExpression,
  type Columns,
  type Node,
  type Value,
} from "./expression";

/**
 * Chip groups that describe the game rather than a play. Per-game stats divide by the games a
 * player appeared in within this scope, so "3rd down, per game" still counts every game played.
 */
export const GAME_SCOPE_GROUP_IDS = ["season", "season_type", "week", "location"] as const;

const ROLE_COLUMNS = ["passer_player_id", "rusher_player_id", "receiver_player_id"] as const;
const SUM_OF_COLUMN = /^SUM\((\w+)\)$/i;

export interface StatQueryParams {
  statIds: string[];
  filterChipState: Record<string, boolean>;
  /** The players to report on, or null for everyone with the stat (a league-wide query). */
  gsisIds: string[] | null;
  /** The season files that hold these players; season chips narrow which of them are read. */
  sources: ColumnSource[];
  /** The tier-1 player-game table; counting stats come from it when no situational filter is on. */
  playerGame?: ColumnSource | null;
  granularity: GranularityMode;
  minPlays: number;
  chipGroups: FilterChipGroup[];
  /** Sorts the finished rows by one of the stats; rows without a value go last. */
  order?: QueryOrder | null;
  /** Keeps the first rows after sorting. */
  limit?: number | null;
  /** One row per player and season or week instead of one per player. */
  split?: Split | null;
  /** Report on teams instead of players: these teams (null for all) on offense or defense. */
  teams?: { ids: string[] | null; side: Side } | null;
}

const TEAM_COLUMN: Readonly<Record<Side, string>> = { offense: "posteam", defense: "defteam" };

type Metric = (rows: ArrayLike<number>, games: number) => Value;

/** Per game is a total over the games played; every other granularity is a plain aggregate. */
function usesGameCount(stat: StatDefinition, granularity: GranularityMode): boolean {
  return (
    !stat.rate_only &&
    SUM_OF_COLUMN.test(stat.base_sql.trim()) &&
    effectiveGranularity(stat, granularity) === "per_game"
  );
}

function metricNodes(stat: StatDefinition, granularity: GranularityMode): Node {
  const sumColumn = stat.rate_only ? null : SUM_OF_COLUMN.exec(stat.base_sql.trim());
  if (!sumColumn) {
    return parseExpression(stat.base_sql);
  }
  return parseExpression(
    effectiveGranularity(stat, granularity) === "per_play" ? `AVG(${sumColumn[1]})` : stat.base_sql,
  );
}

function compileMetric(stat: StatDefinition, granularity: GranularityMode, cols: Columns): Metric {
  const aggregate = compileAggregateExpression(metricNodes(stat, granularity), cols);
  if (!usesGameCount(stat, granularity)) {
    return (rows) => aggregate(rows);
  }
  return (rows, games) => {
    const total = aggregate(rows);
    return typeof total === "number" && games > 0 ? total / games : null;
  };
}

function seasonsSelectedByChips(params: StatQueryParams): Set<number> {
  const years = new Set<number>();
  const group = params.chipGroups.find((g) => g.id === "season");
  for (const option of group?.options ?? []) {
    const match = /^season-(\d+)$/.exec(option.id);
    if (match && params.filterChipState[option.id]) {
      years.add(Number(match[1]));
    }
  }
  return years;
}

function parseOptional(sql: string): Node | null {
  return sql === "" ? null : parseExpression(sql);
}

/** Sorts rows by a stat (rows without a number last) and keeps the first `limit`. */
export function orderAndLimit(result: QueryResult, order: QueryOrder | null, limit: number | null): QueryResult {
  let rows = result.rows;
  if (order) {
    const key = metricSelectAlias(order.metric);
    const sign = order.direction === "asc" ? 1 : -1;
    const isNumber = (v: unknown): v is number => typeof v === "number" && !Number.isNaN(v);
    rows = [...rows].sort((a, b) => {
      const x = a[key];
      const y = b[key];
      return isNumber(x) && isNumber(y) ? (x - y) * sign : Number(!isNumber(x)) - Number(!isNumber(y));
    });
  }
  return { ...result, rows: limit === null ? rows : rows.slice(0, limit) };
}

/** Distinct games per group key (a player or team, or one in a season or week). */
function gamesPlayed(
  cols: Columns,
  rowCount: number,
  wanted: (id: string) => boolean,
  scope: ((row: number) => Value) | null,
  keyOf: (playerId: string, row: number) => string,
  idColumns: readonly string[],
): Map<string, number> {
  const games = new Map<string, Set<unknown>>();
  const gameId = cols.game_id!;
  for (let i = 0; i < rowCount; i++) {
    if (scope && scope(i) !== true) {
      continue;
    }
    for (const role of idColumns) {
      const pid = cols[role]![i];
      if (typeof pid === "string" && wanted(pid)) {
        const key = keyOf(pid, i);
        let set = games.get(key);
        if (!set) {
          set = new Set();
          games.set(key, set);
        }
        set.add(gameId[i]);
      }
    }
  }
  return new Map([...games].map(([pid, set]) => [pid, set.size]));
}

/**
 * Runs the stat query in memory: loads only the columns it reads, filters plays by role, play
 * type, the stat's row filter and the active chips, then aggregates per player.
 */
export async function runStatQuery(
  params: StatQueryParams,
  store: ColumnStore,
  signal?: AbortSignal,
): Promise<QueryResult> {
  const result = await runUnordered(params, store, signal);
  return orderAndLimit(result, params.order ?? null, params.limit ?? null);
}

async function runUnordered(params: StatQueryParams, store: ColumnStore, signal?: AbortSignal): Promise<QueryResult> {
  const teams = params.teams ?? null;
  if (!teams && params.playerGame && canServeFromPlayerGame(params)) {
    return runPlayerGameQuery(params, params.playerGame, store, signal);
  }

  const groups = groupStatsByRows(params.statIds);
  const knownIds = groups.flat().map((s) => s.id);
  if (groups.length === 0) {
    throw new Error("Select at least one stat.");
  }
  if (teams && groups.flat().some((s) => s.category.startsWith("ngs_"))) {
    throw new Error("Next Gen Stats are per-player weekly values, so a team has no total for them.");
  }
  const idColumn = teams ? "team_id" : "player_id";
  const teamColumn = teams ? TEAM_COLUMN[teams.side] : null;
  const groupColumns = splitColumns(params.split);
  const columns = [idColumn, ...groupColumns, ...params.statIds.filter((id) => getStatById(id)).map(metricSelectAlias)];

  const chipYears = seasonsSelectedByChips(params);
  const sources = chipYears.size > 0 ? params.sources.filter((s) => chipYears.has(s.year)) : params.sources;
  if (sources.length === 0) {
    return { columns, rows: [] };
  }

  const needGames = groups.some((g) => g.some((s) => usesGameCount(s, params.granularity)));
  const chipNode = parseOptional(buildFilterWhereSql(params.filterChipState, { groups: params.chipGroups }));
  const scopeNode = needGames
    ? parseOptional(
        buildFilterWhereSql(params.filterChipState, { groups: params.chipGroups, groupIds: GAME_SCOPE_GROUP_IDS }),
      )
    : null;
  const filterNodes = groups.map((g) => (g[0]!.playFilter ? parseExpression(g[0]!.playFilter) : null));

  const needed = new Set<string>();
  const add = (names: Iterable<string>) => {
    for (const n of names) {
      needed.add(n);
    }
  };
  for (const [k, stats] of groups.entries()) {
    add([playerColumnForRole(stats[0]!.playerRole)]);
    if (stats[0]!.playType !== "all") {
      add(["play_type"]);
    }
    for (const stat of stats) {
      add(columnsIn(metricNodes(stat, params.granularity)));
    }
    if (filterNodes[k]) {
      add(columnsIn(filterNodes[k]!));
    }
  }
  if (chipNode) {
    add(columnsIn(chipNode));
  }
  add(groupColumns);
  if (teamColumn) {
    add([teamColumn]);
  }
  if (needGames) {
    add(["game_id", ...(teamColumn ? [teamColumn] : ROLE_COLUMNS)]);
    if (scopeNode) {
      add(columnsIn(scopeNode));
    }
  }

  const table = await store.table(sources, [...needed], signal);
  signal?.throwIfAborted();

  const wanted = wantedPlayers(teams ? teams.ids : params.gsisIds);
  const keyOf = splitKeyer(table.cols, params.split);
  const chip = chipNode ? compileRowExpression(chipNode, table.cols) : null;
  const scope = scopeNode ? compileRowExpression(scopeNode, table.cols) : null;
  const games = needGames
    ? gamesPlayed(table.cols, table.rowCount, wanted, scope, keyOf, teamColumn ? [teamColumn] : ROLE_COLUMNS)
    : new Map<string, number>();
  const minPlays = Math.floor(params.minPlays);

  const results = groups.map((stats, k): QueryResult => {
    const first = stats[0]!;
    const roleIds = table.cols[playerColumnForRole(first.playerRole)]!;
    // A team counts the plays its players would: those with someone in the stat's role.
    const ids = teamColumn ? table.cols[teamColumn]! : roleIds;
    const playTypes = first.playType === "all" ? null : table.cols.play_type!;
    const rowFilter = filterNodes[k] ? compileRowExpression(filterNodes[k]!, table.cols) : null;
    const metrics = stats.map((s) => compileMetric(s, params.granularity, table.cols));

    const rowsByGroup = new Map<string, { pid: string; rows: number[] }>();
    for (let i = 0; i < table.rowCount; i++) {
      const pid = ids[i];
      if (typeof pid !== "string" || !wanted(pid) || typeof roleIds[i] !== "string") {
        continue;
      }
      if (playTypes && playTypes[i] !== first.playType) {
        continue;
      }
      if (rowFilter && rowFilter(i) !== true) {
        continue;
      }
      if (chip && chip(i) !== true) {
        continue;
      }
      const key = keyOf(pid, i);
      let group = rowsByGroup.get(key);
      if (!group) {
        group = { pid, rows: [] };
        rowsByGroup.set(key, group);
      }
      group.rows.push(i);
    }

    const out: Record<string, unknown>[] = [];
    for (const [key, { pid, rows }] of rowsByGroup) {
      if (minPlays > 0 && rows.length < minPlays) {
        continue;
      }
      const row: Record<string, unknown> = { [idColumn]: pid, ...splitValues(table.cols, params.split, rows[0]!) };
      stats.forEach((stat, m) => {
        row[metricSelectAlias(stat.id)] = metrics[m]!(rows, games.get(key) ?? 0);
      });
      out.push(row);
    }
    return { columns: [idColumn, ...groupColumns, ...stats.map((s) => metricSelectAlias(s.id))], rows: out };
  });

  return mergeStatQueryResults(
    results,
    params.statIds.filter((id) => knownIds.includes(id)),
    params.split,
    idColumn,
  );
}
