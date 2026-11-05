import { type Matchup, groupMatchups, isThin } from "@/features/league/logic";
import type { WhatIfRow } from "@/features/league/types";
import { formatPercent } from "@/viz";
import type { SeasonEventRow, WinNeedRow } from "./types";

/** The odds we call "in good shape" for the headline sentence. */
export const GOOD_ODDS = 0.75;
export const ROOT_FOR_LIMIT = 5;

export type NeedLine = { wins: number; games: number; row: WinNeedRow | null };

/** One line per possible win count, 0 to n_games; null where no simulated season had that many wins. */
export function needTable(rows: readonly WinNeedRow[]): NeedLine[] {
  const games = rows[0]?.n_games ?? 0;
  if (rows.length === 0) return [];
  return Array.from({ length: games + 1 }, (_, wins) => ({ wins, games, row: rows.find((r) => r.wins === wins) ?? null }));
}

export function needSentence(rows: readonly WinNeedRow[]): string | null {
  const known = [...rows].sort((a, b) => a.wins - b.wins);
  const last = known[known.length - 1];
  if (!last) return null;
  const good = known.find((r) => r.p_playoffs >= GOOD_ODDS);
  if (good) return `Win ${good.wins} of your next ${good.n_games} and you are at ${formatPercent(good.p_playoffs)} to make the playoffs.`;
  return `Even winning ${last.wins} of your next ${last.n_games} leaves you at ${formatPercent(last.p_playoffs)} to make the playoffs.`;
}

export type RootFor = { key: string; root: string; against: string; gain: number; swing: number };

function rootForMatchup(m: Matchup): RootFor | null {
  const usable = m.outcomes.filter((o) => !isThin(o));
  const best = usable.reduce<WhatIfRow | null>((a, o) => (a === null || o.d_playoffs > a.d_playoffs ? o : a), null);
  if (best === null) return null;
  const worst = usable.reduce((a, o) => (o.d_playoffs < a.d_playoffs ? o : a), best);
  const swing = usable.length > 1 ? best.d_playoffs - worst.d_playoffs : Math.abs(best.d_playoffs);
  return { key: m.key, root: best.winner, against: best.loser, gain: best.d_playoffs, swing };
}

/** Other teams' games this week, biggest swing in my playoff odds first; rare outcomes are left out. */
export function rootFor(rows: readonly WhatIfRow[]): RootFor[] {
  return groupMatchups(rows)
    .filter((m) => !m.involvesMe)
    .flatMap((m) => rootForMatchup(m) ?? [])
    .sort((a, b) => b.swing - a.swing)
    .slice(0, ROOT_FOR_LIMIT);
}

/** Events by the saved run they sit on; those with no run (before the first one) are counted apart. */
export function eventMarks(events: readonly SeasonEventRow[]): { byRun: Map<string, SeasonEventRow[]>; unplaced: SeasonEventRow[] } {
  const byRun = new Map<string, SeasonEventRow[]>();
  const unplaced: SeasonEventRow[] = [];
  for (const e of events) {
    if (e.run_at === null) unplaced.push(e);
    else byRun.set(e.run_at, [...(byRun.get(e.run_at) ?? []), e]);
  }
  return { byRun, unplaced };
}
