/** Sleeper's league page. Team and matchup deep links are undocumented, so this is the deepest link we use. */
export const sleeperLeagueUrl = (leagueId: string): string => `https://sleeper.com/leagues/${encodeURIComponent(leagueId)}`;
