import type { FilterChipGroup } from "@/stat/config/queryBuilderOptions";
import { getStatById, playerColumnForRole, type StatDefinition } from "@/stat/config/statDictionary";
import {
  buildFilterWhereSql,
  effectiveGranularity,
  groupStatsByRows,
  mergeStatQueryResults,
  metricSelectAlias,
  splitColumns,
  splitKeyer,
  splitValues,
} from "@/stat/lib/queryBuilder";
import type { QueryOrder } from "@/stat/lib/queryUrl";
import type { GranularityMode, Side, Split } from "@/stat/types/queryBuilder";
import type { QueryResult } from "@/stat/types/workbench";

import type { ColumnSource, ColumnStore, Table } from "./columns";
import { isLeagueStat, leaguePointsProblem, runLeaguePointsQuery, type LeaguePointsRow } from "./leaguePointsQuery";
import { isDerivedStat, runDerivedStats } from "./derivedQuery";
import { latestGames } from "./lastGames";
import { narrowPlayerSet, playersFitting } from "./playerFilters";
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
export const GAME_SCOPE_GROUP_IDS = ["season", "season_type", "week", "week_number", "opponent", "location"] as const;

export const ROLE_COLUMNS = ["passer_player_id", "rusher_player_id", "receiver_player_id"] as const;

/** A set of players a query is restricted to (`exclude` false) or kept out of (`exclude` true), before ranking. */
export interface PlayerSet {
  ids: string[];
  exclude: boolean;
}

export interface StatQueryParams {
  statIds: string[];
  filterChipState: Record<string, boolean>;
  /** The players to report on, or null for everyone with the stat (a league-wide query). */
  gsisIds: string[] | null;
  /** Narrows the players (named or everyone) to a set, such as a league's free agents; ignored for teams. */
  playerSet?: PlayerSet | null;
  /** The season files that hold these players; season chips narrow which of them are read. */
  sources: ColumnSource[];
  /**
   * The selected league's regular-season weekly points (null when no league is picked); a league
   * stat reads these instead of the shards.
   */
  leaguePoints?: LeaguePointsRow[] | null;
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
  /** Only each player's (or team's) latest N games within the season and week chips; null for all. */
  lastGames?: number | null;
  /** Only players at this position (QB, RB, WR, TE); null for all. Ignored for teams. */
  position?: string | null;
  /** Only players in their rookie season (the one season chip on, else the latest season). Ignored for teams. */
  rookie?: boolean;
  /** The player index (`player_index.parquet`), needed by the position and rookie filters. */
  playerIndex?: ColumnSource | null;
}

export const TEAM_COLUMN: Readonly<Record<Side, string>> = { offense: "posteam", defense: "defteam" };

type Metric = (rows: ArrayLike<number>, games: number) => Value;

/** The argument of a counting stat written as one SUM(...) of a row expression, or null for any other stat. */
export function summedExpression(stat: StatDefinition): Node | null {
  if (stat.rate_only || stat.source !== "pbp") {
    return null;
  }
  const node = parseExpression(stat.base_sql);
  return node.kind === "call" && node.fn === "SUM" && node.args.length === 1 ? node.args[0]! : null;
}

/** Per game is a total over the games played; every other granularity is a plain aggregate. */
function usesGameCount(stat: StatDefinition, granularity: GranularityMode): boolean {
  return summedExpression(stat) !== null && effectiveGranularity(stat, granularity) === "per_game";
}

function metricNodes(stat: StatDefinition, granularity: GranularityMode): Node {
  const summed = summedExpression(stat);
  // Per play, a SUM is the mean of the same expression per row.
  return summed && effectiveGranularity(stat, granularity) === "per_play"
    ? { kind: "call", fn: "AVG", args: [summed] }
    : parseExpression(stat.base_sql);
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

export function seasonsSelectedByChips(params: StatQueryParams): Set<number> {
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
  last: Map<string, Set<unknown>> | null,
): Map<string, number> {
  const games = new Map<string, Set<unknown>>();
  const gameId = cols.game_id!;
  for (let i = 0; i < rowCount; i++) {
    if (scope && scope(i) !== true) {
      continue;
    }
    for (const role of idColumns) {
      const pid = cols[role]![i];
      if (typeof pid === "string" && wanted(pid) && (!last || last.get(pid)?.has(gameId[i]))) {
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
  const chipYears = [...seasonsSelectedByChips(params)];
  const rookieSeason = chipYears.length === 1 ? chipYears[0]! : Math.max(...params.sources.map((s) => s.year));
  const fits = params.teams ? null : await playersFitting(params, rookieSeason, store, signal);
  const narrowed = fits ? { ...params, playerSet: narrowPlayerSet(params.playerSet, fits) } : params;
  const result = await runUnordered(narrowed, store, signal);
  return orderAndLimit(result, params.order ?? null, params.limit ?? null);
}

/** Splits league stats from play stats: each is answered where its data is, then the rows are joined by player. */
async function runUnordered(params: StatQueryParams, store: ColumnStore, signal?: AbortSignal): Promise<QueryResult> {
  const leagueIds = params.statIds.filter(isLeagueStat);
  if (leagueIds.length === 0) {
    return runPlayAndDerived(params, store, signal);
  }
  const problem = leaguePointsProblem(params);
  if (problem) {
    throw new Error(problem);
  }
  const league = runLeaguePointsQuery(params, leagueIds);
  const playIds = params.statIds.filter((id) => !isLeagueStat(id));
  if (playIds.length === 0) {
    return league;
  }
  const plays = await runPlayAndDerived({ ...params, statIds: playIds }, store, signal);
  // The play rows are the base (a left join): minimum plays and role already cut them, and a player
  // with points but no play rows must not pad the table.
  const rowKey = (r: Record<string, unknown>) =>
    ["player_id", ...splitColumns(params.split)].map((c) => String(r[c])).join("|");
  const base = new Set(plays.rows.map(rowKey));
  const kept = { ...league, rows: league.rows.filter((r) => base.has(rowKey(r))) };
  const merged = mergeStatQueryResults([plays, kept], params.statIds, params.split, params.teams ? "team_id" : "player_id");
  return { ...merged, notices: [...(plays.notices ?? []), ...(kept.notices ?? [])] };
}

/** Play stats and derived stats (formulas over play and league stats), each answered on its own, then joined. */
async function runPlayAndDerived(params: StatQueryParams, store: ColumnStore, signal?: AbortSignal): Promise<QueryResult> {
  const derivedIds = params.statIds.filter(isDerivedStat);
  if (derivedIds.length === 0) {
    return runPlayStats(params, store, signal);
  }
  const derived = await runDerivedStats({ ...params, statIds: derivedIds }, store, signal, (parts) =>
    runUnordered(parts, store, signal),
  );
  const plainIds = params.statIds.filter((id) => !isDerivedStat(id));
  if (plainIds.length === 0) {
    return derived;
  }
  const plays = await runPlayStats({ ...params, statIds: plainIds }, store, signal);
  const merged = mergeStatQueryResults([plays, derived], params.statIds, params.split, params.teams ? "team_id" : "player_id");
  return { ...merged, notices: [...(plays.notices ?? []), ...(derived.notices ?? [])] };
}

/** What a play-stat query reads and reports, settled before any data is loaded. */
interface PlayTarget {
  groups: StatDefinition[][];
  idColumn: "team_id" | "player_id";
  /** The team column the stats count by (posteam or defteam), or null for a player query. */
  teamColumn: string | null;
  groupColumns: string[];
  /** The output columns of an empty result. */
  columns: string[];
  /** The season files to read: the chip-selected seasons, else all. */
  sources: ColumnSource[];
}

/** Rejects stats the target cannot answer, then fixes the output columns and the files to read. */
function playTarget(params: StatQueryParams): PlayTarget {
  const teams = params.teams ?? null;
  const groups = groupStatsByRows(params.statIds);
  if (groups.length === 0) {
    throw new Error("Select at least one stat.");
  }
  const teamStat = groups.flat().find((s) => s.teamOnly);
  if (!teams && teamStat) {
    throw new Error(`${teamStat.label} is a team stat: ask about a team, not a player.`);
  }
  if (teams && groups.flat().some((s) => s.category.startsWith("ngs_"))) {
    throw new Error("Next Gen Stats are per-player weekly values, so a team has no total for them.");
  }
  const idColumn = teams ? "team_id" : "player_id";
  const groupColumns = splitColumns(params.split);
  const chipYears = seasonsSelectedByChips(params);
  return {
    groups,
    idColumn,
    teamColumn: teams ? TEAM_COLUMN[teams.side] : null,
    groupColumns,
    columns: [idColumn, ...groupColumns, ...params.statIds.filter((id) => getStatById(id)).map(metricSelectAlias)],
    sources: chipYears.size > 0 ? params.sources.filter((s) => chipYears.has(s.year)) : params.sources,
  };
}

/** The parsed filters and the columns to load for them. */
interface PlayPlan {
  lastN: number | null;
  needGames: boolean;
  chipNode: Node | null;
  /** The chips that describe the game, for per-game counts and last-N games. */
  scopeNode: Node | null;
  /** One play filter per group of stats, null when the group has none. */
  filterNodes: (Node | null)[];
  neededColumns: string[];
}

function planPlayStats(params: StatQueryParams, target: PlayTarget): PlayPlan {
  const { groups, teamColumn, groupColumns } = target;
  const lastN = params.lastGames ?? null;
  const needGames = groups.some((g) => g.some((s) => usesGameCount(s, params.granularity)));
  const chipNode = parseOptional(buildFilterWhereSql(params.filterChipState, { groups: params.chipGroups }));
  const scopeNode = needGames || lastN
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
  if (needGames || lastN) {
    add(["game_id", ...(teamColumn ? [teamColumn] : ROLE_COLUMNS)]);
    if (scopeNode) {
      add(columnsIn(scopeNode));
    }
  }
  if (lastN) {
    add(["season", "week"]);
  }
  return { lastN, needGames, chipNode, scopeNode, filterNodes, neededColumns: [...needed] };
}

/** The loaded plays and the per-query lookups the groups share. */
interface PlayScan {
  table: Table;
  wanted: (id: string) => boolean;
  keyOf: (playerId: string, row: number) => string;
  chip: ((row: number) => Value) | null;
  /** Each id's latest N games when the query asks for them, else null. */
  last: Map<string, Set<unknown>> | null;
  /** Games played per group key, filled only when a stat divides by games. */
  games: Map<string, number>;
}

async function scanPlays(
  params: StatQueryParams,
  target: PlayTarget,
  plan: PlayPlan,
  store: ColumnStore,
  signal?: AbortSignal,
): Promise<PlayScan> {
  const teams = params.teams ?? null;
  const { teamColumn } = target;
  const table = await store.table(target.sources, plan.neededColumns, signal);
  signal?.throwIfAborted();

  const wanted = wantedPlayers(teams ? teams.ids : params.gsisIds, teams ? null : params.playerSet);
  const keyOf = splitKeyer(table.cols, params.split);
  const chip = plan.chipNode ? compileRowExpression(plan.chipNode, table.cols) : null;
  const scope = plan.scopeNode ? compileRowExpression(plan.scopeNode, table.cols) : null;
  const idColumns = teamColumn ? [teamColumn] : ROLE_COLUMNS;
  // A player's games are those he had a play in (any role); a team's, those it played.
  const last = plan.lastN
    ? latestGames(plan.lastN, (addGame) => {
        const { game_id: gameIds, season, week } = table.cols;
        for (let i = 0; i < table.rowCount; i++) {
          if (scope && scope(i) !== true) continue;
          for (const column of idColumns) {
            const pid = table.cols[column]![i];
            if (typeof pid === "string" && wanted(pid)) addGame(pid, gameIds![i], Number(season![i]), Number(week![i]));
          }
        }
      })
    : null;
  const games = plan.needGames
    ? gamesPlayed(table.cols, table.rowCount, wanted, scope, keyOf, idColumns, last)
    : new Map<string, number>();
  return { table, wanted, keyOf, chip, last, games };
}

/** The rows of one group of stats that share a role, play type and filter, aggregated per player (or team) and split. */
function shapeGroup(
  params: StatQueryParams,
  target: PlayTarget,
  plan: PlayPlan,
  scan: PlayScan,
  stats: StatDefinition[],
  k: number,
): QueryResult {
  const { table, wanted, keyOf, chip, last, games } = scan;
  const { idColumn, teamColumn, groupColumns } = target;
  const first = stats[0]!;
  const roleIds = table.cols[playerColumnForRole(first.playerRole)]!;
  // A team counts the plays its players would: those with someone in the stat's role.
  const ids = teamColumn ? table.cols[teamColumn]! : roleIds;
  const playTypes = first.playType === "all" ? null : table.cols.play_type!;
  const filterNode = plan.filterNodes[k];
  const rowFilter = filterNode ? compileRowExpression(filterNode, table.cols) : null;
  const metrics = stats.map((s) => compileMetric(s, params.granularity, table.cols));
  const gameIdAt = last ? table.cols.game_id! : null;
  const minPlays = Math.floor(params.minPlays);

  const rowsByGroup = new Map<string, { pid: string; rows: number[] }>();
  for (let i = 0; i < table.rowCount; i++) {
    const pid = ids[i];
    // A team-only stat counts every play of its type, whoever had the ball.
    if (typeof pid !== "string" || !wanted(pid) || (!first.teamOnly && typeof roleIds[i] !== "string")) {
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
    if (last && !last.get(pid)?.has(gameIdAt![i])) {
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
}

/** Answers play stats from the shards: plan the columns and filters, load and index the plays, then aggregate each group. */
async function runPlayStats(params: StatQueryParams, store: ColumnStore, signal?: AbortSignal): Promise<QueryResult> {
  if (!params.teams && params.playerGame && canServeFromPlayerGame(params)) {
    return runPlayerGameQuery(params, params.playerGame, store, signal);
  }
  const target = playTarget(params);
  if (target.sources.length === 0) {
    return { columns: target.columns, rows: [] };
  }
  const plan = planPlayStats(params, target);
  const scan = await scanPlays(params, target, plan, store, signal);
  const results = target.groups.map((stats, k) => shapeGroup(params, target, plan, scan, stats, k));
  const knownIds = target.groups.flat().map((s) => s.id);
  return mergeStatQueryResults(
    results,
    params.statIds.filter((id) => knownIds.includes(id)),
    params.split,
    target.idColumn,
  );
}
