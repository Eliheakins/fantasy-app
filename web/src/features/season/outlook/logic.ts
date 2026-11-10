import type { OddsHistoryRow, SeasonOddsRow } from "@/lib/outlookTypes";

export const HISTORY_WAIT_MESSAGE = "The odds-over-time chart appears once the simulation has run in two different weeks.";

/** My team exists and saved runs cover at least two weeks (the chart has one point per week). */
export function canShowHistory(odds: readonly SeasonOddsRow[], history: readonly OddsHistoryRow[]): boolean {
  return odds.some((o) => o.is_me) && weeklyHistory(history).length >= 2;
}

export type WeekPoint = { week: number; run_at: string; [rosterId: string]: number | string | null };

/**
 * One point per week from the last saved run in that week, one key per roster id holding p_playoffs.
 * shortcut: runs without `as_of_week` (none in today's archive) are skipped; date them if old archives need it.
 */
export function weeklyHistory(history: readonly OddsHistoryRow[]): WeekPoint[] {
  const lastRun = new Map<number, string>();
  for (const r of history) {
    if (r.as_of_week == null) continue;
    const seen = lastRun.get(r.as_of_week);
    if (seen === undefined || r.run_at > seen) lastRun.set(r.as_of_week, r.run_at);
  }
  const points = new Map<number, WeekPoint>();
  for (const r of history) {
    if (r.as_of_week == null || lastRun.get(r.as_of_week) !== r.run_at) continue;
    const point = points.get(r.as_of_week) ?? { week: r.as_of_week, run_at: r.run_at };
    points.set(r.as_of_week, { ...point, [String(r.roster_id)]: r.p_playoffs });
  }
  return [...points.values()].sort((a, b) => a.week - b.week);
}

/** Week of each saved run, for placing an event on the weekly chart. */
export function runWeeks(history: readonly OddsHistoryRow[]): Map<string, number> {
  return new Map(history.flatMap((r) => (r.as_of_week == null ? [] : [[r.run_at, r.as_of_week] as const])));
}

/** Seeds 1 to 6 make the playoffs; 1 and 2 also get a bye. */
export const PLAYOFF_SEEDS = 6;
export const BYE_SEEDS = 2;

/** Playoff seeds in Forest, the misses light grey. */
export const seedFill = (seed: number): string => (seed <= PLAYOFF_SEEDS ? "var(--lf-forest)" : "var(--lf-chart-other)");

/** Teams in the history with their names, mine first flagged. */
export function historyTeams(
  odds: readonly SeasonOddsRow[],
  history: readonly OddsHistoryRow[],
): { id: string; name: string; isMe: boolean }[] {
  const names = new Map(odds.map((o) => [o.roster_id, o]));
  const ids = [...new Set(history.map((r) => r.roster_id))];
  return ids.map((id) => {
    const row = names.get(id);
    const fallback = history.find((r) => r.roster_id === id)?.team_name ?? String(id);
    return { id: String(id), name: row?.team_name ?? fallback, isMe: row?.is_me ?? false };
  });
}

/** Ranked list: best playoff odds first; ties keep API order. */
export function rankOdds(rows: readonly SeasonOddsRow[]): SeasonOddsRow[] {
  return [...rows].sort((a, b) => (b.p_playoffs ?? -1) - (a.p_playoffs ?? -1));
}

/**
 * Vertical label positions with at least `minGap` between neighbours, kept inside [lo, hi].
 * Returns one y per input, in input order. When the area is too small for the gap, labels overlap
 * rather than leave it.
 */
export function dodgeLabels(ys: readonly number[], minGap: number, lo: number, hi: number): number[] {
  const items = ys.map((y, i) => ({ i, y: Math.min(hi, Math.max(lo, y)) })).sort((a, b) => a.y - b.y);
  let floor = lo;
  const down = items.map((it) => {
    floor = Math.max(it.y, floor);
    const y = floor;
    floor += minGap;
    return { i: it.i, y };
  });
  let ceiling = hi;
  const up = down.reduceRight<{ i: number; y: number }[]>((acc, it) => {
    const y = Math.max(lo, Math.min(it.y, ceiling));
    ceiling = y - minGap;
    return [{ i: it.i, y }, ...acc];
  }, []);
  const out = new Array<number>(ys.length).fill(lo);
  for (const it of up) out[it.i] = it.y;
  return out;
}
