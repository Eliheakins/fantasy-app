/** Stat ids from metrics/metrics.json. */
const RECEIVING = ["rec_receptions", "rec_yards"];
const STATS_BY_POSITION: Readonly<Record<string, readonly string[]>> = {
  QB: ["pass_yards", "pass_tds"],
  RB: ["rush_yards", "rush_tds", ...RECEIVING],
  WR: RECEIVING,
  TE: RECEIVING,
};

/** The stat ids shown for a position's game log; null where there is none (K, DEF, unknown). */
export function statIdsFor(position: string): readonly string[] | null {
  const key = position.toUpperCase();
  return Object.hasOwn(STATS_BY_POSITION, key) ? (STATS_BY_POSITION[key] ?? null) : null;
}

type StatLinkArgs = { gsisId: string | null; position: string; season: number; search?: string };

/**
 * The in-app Find players (Explore) link for a player's weekly game log, keeping the league, team and week of `search` (the
 * current URL's query); null where there is nothing to open (no id, K, DEF).
 */
export function statLink({ gsisId, position, season, search = "" }: StatLinkArgs): string | null {
  const stats = statIdsFor(position);
  if (!gsisId || !stats) return null;
  const query = new URLSearchParams([
    ["p", gsisId],
    ...stats.map((s): [string, string] => ["s", s]),
    ["f", `season-${season}`],
    ["f", "stype-reg"],
    ["by", "week"],
    ["g", "total"],
  ]);
  const current = new URLSearchParams(search);
  for (const shared of ["league", "team", "week"]) {
    const value = current.get(shared);
    if (value !== null) query.set(shared, value);
  }
  return `/players/find?${query.toString()}`;
}

/** The latest NFL season with games: the calendar year from September on, the year before until then. */
export function currentSeason(now: Date = new Date()): number {
  return now.getMonth() < 8 ? now.getFullYear() - 1 : now.getFullYear();
}
