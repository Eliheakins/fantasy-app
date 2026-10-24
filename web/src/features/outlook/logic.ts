import type { OddsHistoryRow, SeasonOddsRow } from "./types";

/** Same message Streamlit shows until the simulation has run twice. */
export const HISTORY_WAIT_MESSAGE =
  "The odds-over-time chart appears after the simulation has run at least twice.";

export type HistoryPoint = { run_at: string; [rosterId: string]: number | string | null };

export function distinctRuns(history: readonly OddsHistoryRow[]): number {
  return new Set(history.map((r) => r.run_at)).size;
}

/** Streamlit's rule: my team exists and at least two saved runs. */
export function canShowHistory(odds: readonly SeasonOddsRow[], history: readonly OddsHistoryRow[]): boolean {
  return odds.some((o) => o.is_me) && distinctRuns(history) >= 2;
}

/** One point per run, one key per roster id holding p_playoffs, oldest run first. */
export function pivotHistory(history: readonly OddsHistoryRow[]): HistoryPoint[] {
  const byRun = new Map<string, HistoryPoint>();
  for (const r of history) {
    const point = byRun.get(r.run_at) ?? { run_at: r.run_at };
    byRun.set(r.run_at, { ...point, [String(r.roster_id)]: r.p_playoffs });
  }
  return [...byRun.values()].sort((a, b) => a.run_at.localeCompare(b.run_at));
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

/** Ranked list: best playoff odds first (Streamlit shows API order); ties keep API order. */
export function rankOdds(rows: readonly SeasonOddsRow[]): SeasonOddsRow[] {
  return [...rows].sort((a, b) => (b.p_playoffs ?? -1) - (a.p_playoffs ?? -1));
}
