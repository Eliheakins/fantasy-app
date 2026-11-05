import type { components } from "@/api/schema";

export type OddsRun = Pick<components["schemas"]["OddsHistoryRow"], "run_at" | "roster_id" | "p_playoffs" | "p_title">;
export type Visit = { at: string; adds: string[] };

const KEY_PREFIX = "fantasy.lastVisit.";
const PERCENT = 100;

const isVisit = (v: unknown): v is Visit => {
  if (typeof v !== "object" || v === null) return false;
  const { at, adds } = v as Record<string, unknown>;
  return typeof at === "string" && !Number.isNaN(Date.parse(at)) && Array.isArray(adds) && adds.every((a) => typeof a === "string");
};

/** The league's last visit, or null on a first visit, with unreadable storage or a value that is not a visit. */
export function readVisit(leagueKey: string): Visit | null {
  try {
    const raw = window.localStorage.getItem(KEY_PREFIX + leagueKey);
    const parsed: unknown = raw === null ? null : JSON.parse(raw);
    return isVisit(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function writeVisit(leagueKey: string, visit: Visit): void {
  try {
    window.localStorage.setItem(KEY_PREFIX + leagueKey, JSON.stringify(visit));
  } catch {
    // Storage can be blocked; the page works, it just has nothing to compare with next time.
  }
}

export const asMs = (runAt: string): number => Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(runAt) ? runAt : `${runAt}Z`);

const diff = (now: number | null, then: number | null): number | null =>
  now === null || then === null ? null : (now - then) * PERCENT;

/**
 * My latest odds against my last run at or before the last visit, in percentage points.
 * Null when no run is that old or none is newer; a missing odd stays null, never zero.
 */
export function oddsSince(history: readonly OddsRun[], rosterId: number, sinceIso: string) {
  const since = Date.parse(sinceIso);
  const mine = history.filter((r) => r.roster_id === rosterId).sort((a, b) => asMs(a.run_at) - asMs(b.run_at));
  const latest = mine[mine.length - 1];
  const before = mine.filter((r) => asMs(r.run_at) <= since).pop();
  if (latest === undefined || before === undefined || asMs(latest.run_at) <= since) return null;
  return { playoffs: diff(latest.p_playoffs, before.p_playoffs), title: diff(latest.p_title, before.p_title), fromRun: before.run_at, toRun: latest.run_at };
}

/** Adds in the current list that the last visit's list did not have; nothing when that list was not stored. */
export function newAdds(current: readonly string[], previous: readonly string[] | undefined): string[] {
  if (previous === undefined) return [];
  return current.filter((name) => !previous.includes(name));
}
