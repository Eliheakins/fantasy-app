import type { FilterChipGroup } from "@/shared/config/queryBuilderOptions";
import { getStatById, playerColumnForRole, type StatDefinition } from "@/shared/config/statDictionary";
import {
  buildFilterWhereSql,
  effectiveGranularity,
  groupStatsByRows,
  mergeStatQueryResults,
  metricSelectAlias,
} from "@/shared/lib/queryBuilder";
import type { GranularityMode } from "@/shared/types/queryBuilder";
import type { QueryResult } from "@/shared/types/workbench";

import type { ColumnSource, ColumnStore } from "./columns";
import { canServeFromPlayerGame, runPlayerGameQuery } from "./playerGameQuery";
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
  gsisIds: string[];
  /** The season files that hold these players; season chips narrow which of them are read. */
  sources: ColumnSource[];
  /** The tier-1 player-game table; counting stats come from it when no situational filter is on. */
  playerGame?: ColumnSource | null;
  granularity: GranularityMode;
  minPlays: number;
  chipGroups: FilterChipGroup[];
}

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
  return parseExpression(effectiveGranularity(stat, granularity) === "per_play" ? `AVG(${sumColumn[1]})` : stat.base_sql);
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

function gamesPlayed(
  cols: Columns,
  rowCount: number,
  wanted: Set<string>,
  scope: ((row: number) => Value) | null,
): Map<string, number> {
  const games = new Map<string, Set<unknown>>();
  const gameId = cols.game_id!;
  for (let i = 0; i < rowCount; i++) {
    if (scope && scope(i) !== true) {
      continue;
    }
    for (const role of ROLE_COLUMNS) {
      const pid = cols[role]![i];
      if (typeof pid === "string" && wanted.has(pid)) {
        let set = games.get(pid);
        if (!set) {
          set = new Set();
          games.set(pid, set);
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
  if (params.playerGame && canServeFromPlayerGame(params)) {
    return runPlayerGameQuery(params, params.playerGame, store, signal);
  }

  const groups = groupStatsByRows(params.statIds);
  const knownIds = groups.flat().map((s) => s.id);
  if (groups.length === 0) {
    throw new Error("Select at least one stat.");
  }
  const columns = ["player_id", ...params.statIds.filter((id) => getStatById(id)).map(metricSelectAlias)];

  const chipYears = seasonsSelectedByChips(params);
  const sources = chipYears.size > 0 ? params.sources.filter((s) => chipYears.has(s.year)) : params.sources;
  if (sources.length === 0) {
    return { columns, rows: [] };
  }

  const needGames = groups.some((g) => g.some((s) => usesGameCount(s, params.granularity)));
  const chipNode = parseOptional(buildFilterWhereSql(params.filterChipState, { groups: params.chipGroups }));
  const scopeNode = needGames
    ? parseOptional(buildFilterWhereSql(params.filterChipState, { groups: params.chipGroups, groupIds: GAME_SCOPE_GROUP_IDS }))
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
  if (needGames) {
    add(["game_id", ...ROLE_COLUMNS]);
    if (scopeNode) {
      add(columnsIn(scopeNode));
    }
  }

  const table = await store.table(sources, [...needed], signal);
  signal?.throwIfAborted();

  const wanted = new Set(params.gsisIds);
  const chip = chipNode ? compileRowExpression(chipNode, table.cols) : null;
  const games = needGames
    ? gamesPlayed(table.cols, table.rowCount, wanted, scopeNode ? compileRowExpression(scopeNode, table.cols) : null)
    : new Map<string, number>();
  const minPlays = Math.floor(params.minPlays);

  const results = groups.map((stats, k): QueryResult => {
    const first = stats[0]!;
    const ids = table.cols[playerColumnForRole(first.playerRole)]!;
    const playTypes = first.playType === "all" ? null : table.cols.play_type!;
    const rowFilter = filterNodes[k] ? compileRowExpression(filterNodes[k]!, table.cols) : null;
    const metrics = stats.map((s) => compileMetric(s, params.granularity, table.cols));

    const rowsByPlayer = new Map<string, number[]>();
    for (let i = 0; i < table.rowCount; i++) {
      const pid = ids[i];
      if (typeof pid !== "string" || !wanted.has(pid)) {
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
      let rows = rowsByPlayer.get(pid);
      if (!rows) {
        rows = [];
        rowsByPlayer.set(pid, rows);
      }
      rows.push(i);
    }

    const out: Record<string, unknown>[] = [];
    for (const [pid, rows] of rowsByPlayer) {
      if (minPlays > 0 && rows.length < minPlays) {
        continue;
      }
      const row: Record<string, unknown> = { player_id: pid };
      stats.forEach((stat, m) => {
        row[metricSelectAlias(stat.id)] = metrics[m]!(rows, games.get(pid) ?? 0);
      });
      out.push(row);
    }
    return { columns: ["player_id", ...stats.map((s) => metricSelectAlias(s.id))], rows: out };
  });

  return mergeStatQueryResults(results, params.statIds.filter((id) => knownIds.includes(id)));
}
