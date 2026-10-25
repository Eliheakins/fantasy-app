import type { PowerRankingRow, WhatIfRow } from "./types";

/** An outcome that happened in fewer runs than this has odds too noisy to show. */
export const MIN_RUNS = 1000;

export type Matchup = { key: string; label: string; involvesMe: boolean; outcomes: WhatIfRow[] };

/** The backend lists a matchup's outcomes together, my game first; group them by team pair. */
export function groupMatchups(rows: readonly WhatIfRow[]): Matchup[] {
  const groups = new Map<string, Matchup>();
  for (const r of rows) {
    const key = [r.winner_id, r.loser_id].sort((a, b) => a - b).join("-");
    const found = groups.get(key);
    if (found) {
      found.outcomes.push(r);
    } else {
      groups.set(key, { key, label: `${r.winner} vs ${r.loser}`, involvesMe: r.involves_me, outcomes: [r] });
    }
  }
  return [...groups.values()];
}

export function isThin(row: Pick<WhatIfRow, "n_runs">): boolean {
  return row.n_runs < MIN_RUNS;
}

/** Bar length as a share of the longest bar; missing or negative values draw nothing. */
export function barFraction(value: number | null | undefined, max: number): number {
  if (value == null || !Number.isFinite(value) || max <= 0) return 0;
  return Math.min(Math.max(value / max, 0), 1);
}

export function formatRecord(wins: number, losses: number, ties: number): string {
  return ties > 0 ? `${wins}-${losses}-${ties}` : `${wins}-${losses}`;
}

/** Toughest remaining schedule first; teams with no games left go last. */
export function scheduleOrder(rows: readonly PowerRankingRow[]): PowerRankingRow[] {
  return [...rows].sort((a, b) => (a.sos_rank ?? Infinity) - (b.sos_rank ?? Infinity));
}
