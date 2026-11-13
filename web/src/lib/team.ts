import type { LooseParams } from "@/api/client";

const TEAMS_ROUTE = "/api/leagues/{league}/teams";

/** Adds `team` (last) to an /api/leagues/{league}/... route's query when a team is being viewed in that league.
 * Roster ids belong to one league, so other leagues' routes (and the team list itself) stay as they are. */
export function withTeam(route: string, params: LooseParams, team: number | null, league: string | null): LooseParams {
  if (team === null || league === null || params.path?.league !== league || route === TEAMS_ROUTE) return params;
  return { ...params, query: { ...params.query, team } };
}

/** The roster id in a `?team=` value, or null when absent or not a whole number. */
export function parseTeam(value: string | null): number | null {
  return value !== null && /^\d+$/.test(value) ? Number(value) : null;
}
