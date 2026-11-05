/** Links to the stat app (a separate app for now); its URL contract is in nfl-stat-app's README. */
const DEFAULT_BASE = "http://localhost:3000";
const STAT_BASE: string = import.meta.env.VITE_STAT_APP_URL || DEFAULT_BASE;

/** Stat ids from nfl-stat-app's metrics/metrics.json. */
const RECEIVING = ["rec_receptions", "rec_yards"];
const STATS_BY_POSITION: Readonly<Record<string, readonly string[]>> = {
  QB: ["pass_yards", "pass_tds"],
  RB: ["rush_yards", "rush_tds", ...RECEIVING],
  WR: RECEIVING,
  TE: RECEIVING,
};

type StatLinkArgs = { gsisId: string | null; position: string; season: number; base?: string };

/** The stat app's weekly game log for one player, or null where there is nothing to open (no id, K, DEF). */
export function statLink({ gsisId, position, season, base = STAT_BASE }: StatLinkArgs): string | null {
  const key = position.toUpperCase();
  const stats = Object.hasOwn(STATS_BY_POSITION, key) ? STATS_BY_POSITION[key] : undefined;
  if (!gsisId || !stats) return null;
  const query = [
    `p=${encodeURIComponent(gsisId)}`,
    ...stats.map((s) => `s=${s}`),
    `f=season-${season}`,
    "f=stype-reg",
    "by=week",
    "g=total",
  ].join("&");
  return `${base.replace(/\/+$/, "")}/explore?${query}`;
}

/** The latest NFL season with games: the calendar year from September on, the year before until then. */
export function currentSeason(now: Date = new Date()): number {
  return now.getMonth() < 8 ? now.getFullYear() - 1 : now.getFullYear();
}
