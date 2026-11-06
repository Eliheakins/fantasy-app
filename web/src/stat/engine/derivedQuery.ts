/**
 * Derived stats: a formula over other stats' totals, for what one role's plays cannot give.
 * Scrimmage yards (rushing plus receiving), passer rating and fantasy points add or combine several
 * stats; shares divide a player's total by his team's. In a formula:
 *   - a metric id is that stat's total for the row (0 when the player has none of its plays);
 *   - `team__<id>` is the team's total of that stat in the games the player played, for the team he
 *     played for in each (a traded player's share uses his own team's games);
 *   - `games` is the games the player (or team) played in the query's scope.
 * A counting formula per game divides by `games`; a rate formula is used as written.
 */
import { getStatById, playerColumnForRole, type StatDefinition } from "@/stat/config/statDictionary";
import { buildFilterWhereSql, metricSelectAlias, splitColumns, splitKeyer } from "@/stat/lib/queryBuilder";
import type { QueryResult } from "@/stat/types/workbench";

import type { ColumnStore } from "./columns";
import {
  type Columns,
  columnsIn,
  compileAggregateExpression,
  compileRowExpression,
  type Node,
  parseExpression,
} from "./expression";
import { latestGames } from "./lastGames";
import { wantedPlayers } from "./playerGameQuery";
import {
  GAME_SCOPE_GROUP_IDS,
  ROLE_COLUMNS,
  seasonsSelectedByChips,
  type StatQueryParams,
  summedExpression,
  TEAM_COLUMN,
} from "./statQuery";

const TEAM_PREFIX = "team__";
const GAMES = "games";

export const isDerivedStat = (id: string): boolean => getStatById(id)?.source === "derived";

/** The stat ids, team totals and games a set of formulas reads. */
function partsOf(nodes: readonly Node[]): { stats: string[]; team: string[]; games: boolean } {
  const names = new Set(nodes.flatMap((n) => columnsIn(n)));
  const team = [...names].filter((n) => n.startsWith(TEAM_PREFIX)).map((n) => n.slice(TEAM_PREFIX.length));
  const stats = [...names].filter((n) => !n.startsWith(TEAM_PREFIX) && n !== GAMES);
  for (const id of [...stats, ...team]) {
    const stat = getStatById(id);
    if (!stat || stat.source === "derived") {
      throw new Error(`A formula names '${id}', which is not a play or league stat.`);
    }
  }
  return { stats: [...new Set([...stats, ...team])], team, games: names.has(GAMES) };
}

const parseOptional = (sql: string): Node | null => (sql === "" ? null : parseExpression(sql));

/**
 * Team totals of `teamStats` in each player's games, and the games each player (or team) played, by
 * the row key (the player or team, and the split). One pass over the play-by-play.
 */
async function teamTotalsAndGames(
  params: StatQueryParams,
  teamStats: StatDefinition[],
  store: ColumnStore,
  signal: AbortSignal | undefined,
): Promise<{ team: Map<string, Record<string, number>>; games: Map<string, number> }> {
  const years = seasonsSelectedByChips(params);
  const sources = years.size > 0 ? params.sources.filter((s) => years.has(s.year)) : params.sources;
  const chipNode = parseOptional(buildFilterWhereSql(params.filterChipState, { groups: params.chipGroups }));
  const scopeNode = parseOptional(
    buildFilterWhereSql(params.filterChipState, { groups: params.chipGroups, groupIds: GAME_SCOPE_GROUP_IDS }),
  );
  const teamColumn = params.teams ? TEAM_COLUMN[params.teams.side] : null;
  const idColumns: readonly string[] = teamColumn ? [teamColumn] : ROLE_COLUMNS;
  const parts = teamStats.map((stat) => {
    const summed = summedExpression(stat);
    if (!summed) {
      throw new Error(`${stat.label} is not a count, so a team total of it cannot be added up.`);
    }
    return { stat, summed, filter: stat.playFilter ? parseExpression(stat.playFilter) : null };
  });

  const needed = new Set<string>(["game_id", "posteam", "season", "week", ...idColumns, ...splitColumns(params.split)]);
  for (const node of [chipNode, scopeNode, ...parts.flatMap((p) => [p.summed, p.filter])]) {
    if (node) columnsIn(node).forEach((c) => needed.add(c));
  }
  for (const { stat } of parts) {
    needed.add(playerColumnForRole(stat.playerRole));
    needed.add("play_type");
  }
  const table = await store.table(sources, [...needed], signal);
  signal?.throwIfAborted();
  const { cols, rowCount } = table;
  const chip = chipNode ? compileRowExpression(chipNode, cols) : null;
  const scope = scopeNode ? compileRowExpression(scopeNode, cols) : null;
  const wanted = wantedPlayers(params.teams ? params.teams.ids : params.gsisIds, params.teams ? null : params.playerSet);
  const keyOf = splitKeyer(cols, params.split);
  const gameId = cols.game_id!;
  const posteam = cols.posteam!;
  const inScope = (i: number) => !scope || scope(i) === true;

  const last = params.lastGames
    ? latestGames(params.lastGames, (addGame) => {
        for (let i = 0; i < rowCount; i++) {
          if (!inScope(i)) continue;
          for (const column of idColumns) {
            const id = cols[column]![i];
            if (typeof id === "string" && wanted(id)) addGame(id, gameId[i], Number(cols.season![i]), Number(cols.week![i]));
          }
        }
      })
    : null;

  // The games (with the team the player had the ball for) behind each row key.
  const gamesByKey = new Map<string, Set<string>>();
  for (let i = 0; i < rowCount; i++) {
    if (!inScope(i)) continue;
    for (const column of idColumns) {
      const id = cols[column]![i];
      if (typeof id !== "string" || !wanted(id) || (last && !last.get(id)?.has(gameId[i]))) continue;
      const key = keyOf(id, i);
      const set = gamesByKey.get(key) ?? new Set<string>();
      set.add(`${String(gameId[i])}|${String(posteam[i])}`);
      gamesByKey.set(key, set);
    }
  }

  // Each team's total of each stat in each game, under the same chips as the player's own plays.
  const perGame = new Map<string, Record<string, number>>();
  for (const { stat, summed, filter } of parts) {
    const rowsByGame = new Map<string, number[]>();
    const roleIds = cols[playerColumnForRole(stat.playerRole)]!;
    const rowFilter = filter ? compileRowExpression(filter, cols) : null;
    for (let i = 0; i < rowCount; i++) {
      if (typeof roleIds[i] !== "string" || (stat.playType !== "all" && cols.play_type![i] !== stat.playType)) continue;
      if ((rowFilter && rowFilter(i) !== true) || (chip && chip(i) !== true)) continue;
      const game = `${String(gameId[i])}|${String(posteam[i])}`;
      const rows = rowsByGame.get(game) ?? [];
      rows.push(i);
      rowsByGame.set(game, rows);
    }
    const sum = compileAggregateExpression({ kind: "call", fn: "SUM", args: [summed] }, cols);
    for (const [game, rows] of rowsByGame) {
      const totals = perGame.get(game) ?? {};
      totals[stat.id] = Number(sum(rows) ?? 0);
      perGame.set(game, totals);
    }
  }

  const team = new Map<string, Record<string, number>>();
  const games = new Map<string, number>();
  for (const [key, set] of gamesByKey) {
    const totals: Record<string, number> = {};
    for (const { stat } of parts) {
      totals[stat.id] = [...set].reduce((n, game) => n + (perGame.get(game)?.[stat.id] ?? 0), 0);
    }
    team.set(key, totals);
    games.set(key, new Set([...set].map((g) => g.split("|")[0])).size);
  }
  return { team, games };
}

/**
 * Answers the derived stats of a query. `runPlain` answers the play and league stats a formula reads,
 * as totals with no cut, so a part's own minimum, order and limit cannot drop a row.
 */
export async function runDerivedStats(
  params: StatQueryParams,
  store: ColumnStore,
  signal: AbortSignal | undefined,
  runPlain: (params: StatQueryParams) => Promise<QueryResult>,
): Promise<QueryResult> {
  const stats = params.statIds.map((id) => getStatById(id)!).filter((s) => s.source === "derived");
  const formulas = stats.map((s) => parseExpression(s.formula!));
  const volumes = stats.map((s) => (s.volume ? parseExpression(s.volume) : null));
  const parts = partsOf([...formulas, ...volumes.flatMap((v) => (v ? [v] : []))]);
  if (params.teams && parts.team.length > 0) {
    throw new Error("A share compares a player with his team, so a team has none.");
  }
  const idColumn = params.teams ? "team_id" : "player_id";
  const groupColumns = splitColumns(params.split);
  const aliases = stats.map((s) => metricSelectAlias(s.id));

  const base = await runPlain({ ...params, statIds: parts.stats, granularity: "total", minPlays: 0, order: null, limit: null });
  const perGame = stats.some((s) => !s.rate_only) && params.granularity !== "total";
  const extra =
    parts.team.length > 0 || parts.games || perGame
      ? await teamTotalsAndGames(params, parts.team.map((id) => getStatById(id)!), store, signal)
      : { team: new Map<string, Record<string, number>>(), games: new Map<string, number>() };

  const keyOf = (row: Record<string, unknown>) => [row[idColumn], ...groupColumns.map((c) => row[c])].join("|");
  const keys = base.rows.map(keyOf);
  // Each part as a column over the base rows: a stat the player has no plays for counts 0.
  const cols: Columns = {
    [GAMES]: keys.map((k) => extra.games.get(k) ?? null),
    ...Object.fromEntries(parts.stats.map((id) => [id, base.rows.map((r) => Number(r[metricSelectAlias(id)] ?? 0))])),
    ...Object.fromEntries(parts.team.map((id) => [`${TEAM_PREFIX}${id}`, keys.map((k) => extra.team.get(k)?.[id] ?? null)])),
  };
  const values = formulas.map((f) => compileRowExpression(f, cols));
  const volumeOf = volumes.map((v) => (v ? compileRowExpression(v, cols) : null));
  const minPlays = Math.floor(params.minPlays);

  const rows = base.rows.flatMap((row, i) => {
    const out: Record<string, unknown> = { [idColumn]: row[idColumn], ...Object.fromEntries(groupColumns.map((c) => [c, row[c]])) };
    let kept = false;
    stats.forEach((stat, k) => {
      const volume = volumeOf[k];
      if (minPlays > 0 && volume && Number(volume(i) ?? 0) < minPlays) {
        out[aliases[k]!] = null;
        return;
      }
      const value = values[k]!(i);
      const games = extra.games.get(keys[i]!) ?? 0;
      out[aliases[k]!] =
        typeof value !== "number" ? null : !stat.rate_only && perGame ? (games > 0 ? value / games : null) : value;
      kept = true;
    });
    return kept ? [out] : [];
  });
  return { columns: [idColumn, ...groupColumns, ...aliases], rows, notices: base.notices };
}
