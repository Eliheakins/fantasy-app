const LEAGUE_URL = /^\/api\/leagues\/([^/?]+)\/(.+)$/;
const TEAMS_PATH = /^teams(\?|$)/;

/** Adds `team=` to an /api/leagues/{league}/... url when a team is being viewed in that league.
 * Roster ids belong to one league, so other leagues' urls (and the team list itself) stay as is. */
export function withTeam(url: string, team: number | null, league: string | null): string {
  if (team === null || league === null) return url;
  const [, key, path] = LEAGUE_URL.exec(url) ?? [];
  if (key === undefined || path === undefined) return url;
  if (decodeURIComponent(key) !== league || TEAMS_PATH.test(path)) return url;
  return `${url}${url.includes("?") ? "&" : "?"}team=${team}`;
}

/** The roster id in a `?team=` value, or null when absent or not a whole number. */
export function parseTeam(value: string | null): number | null {
  return value !== null && /^\d+$/.test(value) ? Number(value) : null;
}
