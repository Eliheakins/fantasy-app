import type { PowerRankingRow, TeamGradeRow, WhatIfRow } from "./types";

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

export const GRADE_POSITIONS = ["overall", "QB", "RB", "WR", "TE"] as const;
export type GradePosition = (typeof GRADE_POSITIONS)[number];
export type GradeTeam = {
  roster_id: number;
  team_name: string;
  is_me: boolean;
  cells: Partial<Record<GradePosition, TeamGradeRow>>;
};

/** One entry per team, best overall first; a team without an overall row goes last. */
export function gradeGrid(rows: readonly TeamGradeRow[]): GradeTeam[] {
  const teams = new Map<number, GradeTeam>();
  for (const r of rows) {
    const team = teams.get(r.roster_id) ?? { roster_id: r.roster_id, team_name: r.team_name, is_me: r.is_me, cells: {} };
    team.cells[r.position as GradePosition] = r;
    teams.set(r.roster_id, team);
  }
  const rank = (t: GradeTeam) => t.cells.overall?.rank ?? Infinity;
  return [...teams.values()].sort((a, b) => rank(a) - rank(b) || a.roster_id - b.roster_id);
}

const SUFFIXES: Record<number, string> = { 1: "st", 2: "nd", 3: "rd" };

/** 1 -> "1st", 2 -> "2nd", 11 -> "11th", 23 -> "23rd". */
export function ordinal(n: number): string {
  const tens = n % 100;
  const suffix = tens >= 11 && tens <= 13 ? "th" : (SUFFIXES[n % 10] ?? "th");
  return `${n}${suffix}`;
}
