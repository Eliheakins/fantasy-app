import type { FilterChipGroup } from "@/stat/config/queryBuilderOptions";
import { getStatById } from "@/stat/config/statDictionary";
import {
  buildFilterWhereSql,
  mergeStatQueryResults,
  metricSelectAlias,
  splitColumns,
  splitKeyer,
  splitValues,
} from "@/stat/lib/queryBuilder";
import type { QueryResult } from "@/stat/types/workbench";

import { compileRowExpression, parseExpression } from "./expression";
import { latestGames } from "./lastGames";
import type { StatQueryParams } from "./statQuery";
import { wantedPlayers } from "./playerGameQuery";

/** One player's regular-season points in one week under the selected league's scoring. */
export interface LeaguePointsRow {
  gsis_id: string;
  season: number;
  week: number;
  points: number;
}

/** Chip groups a weekly points row can answer: it knows its season, season type (always regular) and week. */
const GAME_LEVEL_GROUP_IDS = ["season", "season_type", "week", "week_number"] as const;

export const isLeagueStat = (id: string): boolean => getStatById(id)?.source === "league";

/** Labels of the groups with a chip on that need the plays themselves, which league points are not made of. */
function playLevelGroups(params: StatQueryParams): string[] {
  return params.chipGroups
    .filter(
      (g: FilterChipGroup) =>
        !(GAME_LEVEL_GROUP_IDS as readonly string[]).includes(g.id) && g.options.some((o) => params.filterChipState[o.id]),
    )
    .map((g) => g.label);
}

/** The error a query gets when it cannot have league points, or null when it can. */
export function leaguePointsProblem(params: StatQueryParams): string | null {
  if (params.teams) {
    return "League points are for players, not teams.";
  }
  if (!params.leaguePoints) {
    return "League points use the league picked at the top of the page. Pick a league, then run again.";
  }
  return null;
}

/**
 * Answers the league-sourced stats of a query. The rows already carry gsis_id, season and week, so
 * the filters, split, ranking and per-game count work on them the way they do on the player-game
 * table; per game divides by the weeks that have a points row. A situational filter makes no sense
 * for a weekly total, so it yields no rows and a notice rather than unfiltered numbers.
 */
export function runLeaguePointsQuery(params: StatQueryParams, statIds: string[]): QueryResult {
  const groupColumns = splitColumns(params.split);
  const aliases = statIds.map(metricSelectAlias);
  const empty: QueryResult = { columns: ["player_id", ...groupColumns, ...aliases], rows: [] };

  const ignored = playLevelGroups(params);
  if (ignored.length > 0) {
    const labels = statIds.map((id) => getStatById(id)?.label ?? id).join(", ");
    return { ...empty, notices: [`${labels} is a weekly total, so ${ignored.join(", ")} filters cannot apply to it: no numbers shown.`] };
  }

  const notices =
    params.filterChipState["stype-post"] && !params.filterChipState["stype-reg"] ? ["League points are regular season only."] : [];
  const points = params.leaguePoints ?? [];
  const cols = {
    gsis_id: points.map((r) => r.gsis_id),
    season: points.map((r) => r.season),
    week: points.map((r) => r.week),
    season_type: points.map(() => "REG"),
  };
  const where = buildFilterWhereSql(params.filterChipState, {
    groups: params.chipGroups,
    groupIds: GAME_LEVEL_GROUP_IDS,
  });
  const keep = where === "" ? null : compileRowExpression(parseExpression(where), cols);
  const wanted = wantedPlayers(params.gsisIds, params.playerSet);
  const keyOf = splitKeyer(cols, params.split);

  const inScope = (i: number): boolean => wanted(cols.gsis_id[i]!) && (!keep || keep(i) === true);
  // One row per player and week, so a row index stands for its game.
  const last = params.lastGames
    ? latestGames(params.lastGames, (addGame) => {
        for (let i = 0; i < points.length; i++) {
          if (inScope(i)) addGame(cols.gsis_id[i]!, i, cols.season[i]!, cols.week[i]!);
        }
      })
    : null;
  const groups = new Map<string, { playerId: string; rows: number[] }>();
  for (let i = 0; i < points.length; i++) {
    const id = cols.gsis_id[i]!;
    if (inScope(i) && (!last || last.get(id)?.has(i))) {
      const key = keyOf(id, i);
      const group = groups.get(key) ?? { playerId: id, rows: [] };
      group.rows.push(i);
      groups.set(key, group);
    }
  }

  const rows = [...groups.values()].map(({ playerId, rows: games }) => {
    const total = games.reduce((n, g) => n + points[g]!.points, 0);
    // shortcut: per game divides by weeks that have a points row, so a week with no row (bye, inactive) is not a game; upgrade if player_points ever stores inactive weeks.
    const value = params.granularity === "total" ? total : total / games.length;
    return {
      player_id: playerId,
      ...splitValues(cols, params.split, games[0]!),
      ...Object.fromEntries(aliases.map((a) => [a, value])),
    };
  });
  const merged = mergeStatQueryResults([{ ...empty, rows }], statIds, params.split);
  return notices.length > 0 ? { ...merged, notices } : merged;
}
