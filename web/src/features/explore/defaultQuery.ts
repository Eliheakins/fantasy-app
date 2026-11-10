import { EMPTY_QUERY, type QueryState } from "@/stat/lib/queryUrl";

const DEFAULT_ROWS = 25;
const DEFAULT_MIN_PLAYS = 20;

/** The query Find players opens on: the latest season's top receivers by targets per game, regular season. */
export function defaultQuery(latestSeason: number): QueryState {
  return {
    ...EMPTY_QUERY,
    stats: ["rec_tgt"],
    filters: [`season-${latestSeason}`, "stype-reg"],
    granularity: "per_game",
    minPlays: DEFAULT_MIN_PLAYS,
    order: { metric: "rec_tgt", direction: "desc" },
    limit: DEFAULT_ROWS,
    position: "WR",
  };
}

/** True when the query holds nothing the user chose, so the default can take its place. */
export function isBlankQuery(state: QueryState): boolean {
  return state.stats.length === 0 && state.players.length === 0 && state.teams.length === 0 && state.filters.length === 0;
}
