import type { BracketMatch, BracketRound, BracketSide, OddsHistoryRow, SeasonOddsRow } from "@/lib/outlookTypes";

export const HISTORY_WAIT_MESSAGE = "The odds-over-time chart appears once the simulation has run in two different weeks.";

/** My team exists and saved runs cover at least two weeks (the chart has one point per week). */
export function canShowHistory(odds: readonly SeasonOddsRow[], history: readonly OddsHistoryRow[]): boolean {
  return odds.some((o) => o.is_me) && weeklyHistory(history).length >= 2;
}

export type WeekPoint = { week: number; run_at: string; [rosterId: string]: number | string | null };

/**
 * One point per week from the last saved run in that week, one key per roster id holding p_playoffs
 * (p_title from `titleFromWeek` on: playoff odds are flat 0 or 1 once the bracket is set).
 * shortcut: runs without `as_of_week` (none in today's archive) are skipped; date them if old archives need it.
 */
export function weeklyHistory(history: readonly OddsHistoryRow[], titleFromWeek?: number | null): WeekPoint[] {
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
    const title = titleFromWeek != null && r.as_of_week >= titleFromWeek;
    points.set(r.as_of_week, { ...point, [String(r.roster_id)]: title ? r.p_title : r.p_playoffs });
  }
  return [...points.values()].sort((a, b) => a.week - b.week);
}

/** Week of each saved run, for placing an event on the weekly chart. */
export function runWeeks(history: readonly OddsHistoryRow[]): Map<string, number> {
  return new Map(history.flatMap((r) => (r.as_of_week == null ? [] : [[r.run_at, r.as_of_week] as const])));
}

/** Seeds 1 to `playoffTeams` make the playoffs; in a 6-team bracket 1 and 2 also get a bye. */
export const byeSeeds = (playoffTeams: number): number => (playoffTeams === 6 ? 2 : 0);

/** Playoff seeds in Forest, the misses light grey. */
export const seedFill = (seed: number, playoffTeams: number): string =>
  seed <= playoffTeams ? "var(--lf-forest)" : "var(--lf-chart-other)";

/** The seed chart's caption for a league's bracket. */
export function seedCaption(playoffTeams: number): string {
  const bye = byeSeeds(playoffTeams);
  const byes = bye > 0 ? `; ${bye === 2 ? "1 and 2" : `1 to ${bye}`} get a bye` : "";
  return `Chance of each regular-season seed. Seeds 1 to ${playoffTeams} make the playoffs${byes}.`;
}

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

/** First week of the first round, or null without a bracket. */
export function playoffStartWeek(rounds: readonly BracketRound[]): number | null {
  const weeks = rounds.flatMap((r) => r.weeks);
  return weeks.length ? Math.min(...weeks) : null;
}

export function roundHeading(r: BracketRound): string {
  return `Round ${r.round}, ${r.weeks.length > 1 ? "weeks" : "week"} ${r.weeks.join(" and ")}`;
}

function sideText(s: BracketSide, myId: number | null): string {
  if (s.roster_id === null) return `${s.from_kind === "l" ? "loser" : "winner"} of match ${s.from_m}`;
  const seed = s.seed === null ? "" : `seed ${s.seed} `;
  return `${seed}${s.team_name ?? "Team"}${s.roster_id === myId ? " (you)" : ""}`;
}

const sentence = (text: string) => `${text.charAt(0).toUpperCase()}${text.slice(1)}`;
const name = (s: BracketSide) => s.team_name ?? "Team";

/** One match as a sentence: who plays, then who won or each side's chance to advance. Winner/loser sides are named by their match. */
export function matchText(m: BracketMatch, myId: number | null): string {
  const pair = `${sentence(sideText(m.t1, myId))} vs ${sideText(m.t2, myId)}.`;
  const winner = [m.t1, m.t2].find((s) => s.roster_id !== null && s.roster_id === m.winner);
  if (winner) return `${pair} ${name(winner)} won.`;
  const sides: [BracketSide, number | null][] = [
    [m.t1, m.t1_p_win],
    [m.t2, m.t2_p_win],
  ];
  const odds = sides.filter((x): x is [BracketSide, number] => x[0].roster_id !== null && x[1] !== null);
  const [first, second] = odds;
  if (!first) return pair;
  const pct = (p: number) => `${Math.round(p * 100)}%`;
  return `${pair} ${name(first[0])} ${pct(first[1])} to advance${second ? `, ${name(second[0])} ${pct(second[1])}` : ""}.`;
}

/** "Champion", "Eliminated in round N" (the first match I lost), or null while I am alive or without a team. */
export function myBracketStatus(rounds: readonly BracketRound[], myId: number | null): string | null {
  if (myId === null) return null;
  const mine = rounds.flatMap((r) =>
    r.matches.filter((m) => m.winner !== null && (m.t1.roster_id === myId || m.t2.roster_id === myId)).map((m) => ({ round: r.round, m })),
  );
  const lost = [...mine].sort((a, b) => a.round - b.round).find((x) => x.m.winner !== myId);
  if (lost) return `Eliminated in round ${lost.round}`;
  return mine.some((x) => x.m.place === 1) ? "Champion" : null;
}
