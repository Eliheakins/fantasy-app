import { getStatById, type PlayerRole, type StatDefinition } from "@/shared/config/statDictionary";
import {
  buildFilterWhereSql,
  mergeStatQueryResults,
  metricSelectAlias,
  splitColumns,
  splitKeyer,
  splitValues,
} from "@/shared/lib/queryBuilder";
import type { QueryResult } from "@/shared/types/workbench";

import type { ColumnSource, ColumnStore } from "./columns";
import { columnsIn, compileRowExpression, parseExpression } from "./expression";
import type { StatQueryParams } from "./statQuery";

/**
 * Tier 1: one row per player per game with the official counting totals. It answers a counting stat
 * when no filter needs the plays themselves, and is far smaller than the play-by-play shards.
 */

/** Chip groups the table can answer: it knows each game's season, season type and week. */
const PLAYER_GAME_GROUP_IDS = new Set(["season", "season_type", "week"]);

/** The column that counts a role's plays, for the minimum-plays cut and for games played. */
const VOLUME_COLUMN: Readonly<Record<PlayerRole, string>> = {
  passer: "attempts",
  rusher: "carries",
  receiver: "targets",
};

/** The stats a query names, or null when any is unknown or cannot come from the table. */
function tierOneStats(params: StatQueryParams): StatDefinition[] | null {
  const stats = params.statIds.map((id) => getStatById(id));
  const servable = stats.every((s) => s?.playerGameColumn !== undefined && !s.rate_only);
  return stats.length > 0 && servable ? (stats as StatDefinition[]) : null;
}

/** True when the table can answer the whole query: counting stats, any granularity, no situational chip. */
export function canServeFromPlayerGame(params: StatQueryParams): boolean {
  if (!params.playerGame || !tierOneStats(params)) {
    return false;
  }
  return !params.chipGroups.some(
    (g) => !PLAYER_GAME_GROUP_IDS.has(g.id) && g.options.some((o) => params.filterChipState[o.id]),
  );
}

/** Who a query reports on: the named players, or everyone when none are named. */
export const wantedPlayers = (gsisIds: string[] | null): ((id: string) => boolean) => {
  const named = gsisIds === null ? null : new Set(gsisIds);
  return (id) => named === null || named.has(id);
};

const numberAt = (column: ArrayLike<unknown>, row: number): number => Number(column[row]) || 0;

/** Answers a query that `canServeFromPlayerGame` accepted, reading only the table's columns it needs. */
export async function runPlayerGameQuery(
  params: StatQueryParams,
  source: ColumnSource,
  store: ColumnStore,
  signal?: AbortSignal,
): Promise<QueryResult> {
  const stats = tierOneStats(params) ?? [];
  const where = buildFilterWhereSql(params.filterChipState, { groups: params.chipGroups });
  const whereNode = where === "" ? null : parseExpression(where);

  const byRole = new Map<PlayerRole, StatDefinition[]>();
  for (const stat of stats) {
    byRole.set(stat.playerRole, [...(byRole.get(stat.playerRole) ?? []), stat]);
  }

  const groupColumns = splitColumns(params.split);
  const needed = new Set(["gsis_id", ...groupColumns, ...(whereNode ? columnsIn(whereNode) : [])]);
  for (const [role, roleStats] of byRole) {
    needed.add(VOLUME_COLUMN[role]);
    roleStats.forEach((s) => needed.add(s.playerGameColumn!));
  }
  const table = await store.table([source], [...needed], signal);
  signal?.throwIfAborted();

  const keep = whereNode ? compileRowExpression(whereNode, table.cols) : null;
  const wanted = wantedPlayers(params.gsisIds);
  const ids = table.cols.gsis_id!;
  const keyOf = splitKeyer(table.cols, params.split);
  const rowsByGroup = new Map<string, { playerId: string; games: number[] }>();
  for (let i = 0; i < table.rowCount; i++) {
    const id = ids[i];
    if (typeof id === "string" && wanted(id) && (!keep || keep(i) === true)) {
      const key = keyOf(id, i);
      const group = rowsByGroup.get(key) ?? { playerId: id, games: [] };
      group.games.push(i);
      rowsByGroup.set(key, group);
    }
  }

  const minPlays = Math.floor(params.minPlays);
  const results = [...byRole].map(([role, roleStats]): QueryResult => {
    const volume = table.cols[VOLUME_COLUMN[role]]!;
    const rows: Record<string, unknown>[] = [];
    for (const { playerId, games } of rowsByGroup.values()) {
      const played = games.filter((g) => numberAt(volume, g) > 0);
      const plays = played.reduce((n, g) => n + numberAt(volume, g), 0);
      if (plays === 0 || plays < minPlays) {
        continue;
      }
      const row: Record<string, unknown> = { player_id: playerId, ...splitValues(table.cols, params.split, games[0]!) };
      for (const stat of roleStats) {
        const column = table.cols[stat.playerGameColumn!]!;
        const total = games.reduce((n, g) => n + numberAt(column, g), 0);
        const divisor = { total: 1, per_game: played.length, per_play: plays }[params.granularity];
        row[metricSelectAlias(stat.id)] = total / divisor;
      }
      rows.push(row);
    }
    return { columns: ["player_id", ...groupColumns, ...roleStats.map((s) => metricSelectAlias(s.id))], rows };
  });

  return mergeStatQueryResults(results, params.statIds, params.split);
}
