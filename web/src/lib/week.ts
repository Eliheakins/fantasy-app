import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { clampWeek, FIRST_WEEK, LAST_WEEK } from "@/features/scoreboard/logic";
import { useLeague } from "@/lib/league";

const isWeek = (n: number): boolean => Number.isInteger(n) && n >= FIRST_WEEK && n <= LAST_WEEK;

/** The selected league's current week (week 1 until the league list loads). */
export function useCurrentWeek(): number {
  const { league, leagues } = useLeague();
  const current = leagues.kind === "ready" ? leagues.data.find((l) => l.league_key === league)?.current_week : null;
  return clampWeek(current ?? FIRST_WEEK);
}

/** The global week: `?week=`, else the selected league's current week, else week 1. Every page reads it here. */
export function useWeek(): { week: number; setWeek: (week: number) => void } {
  const current = useCurrentWeek();
  const [params, setParams] = useSearchParams();
  const asked = Number(params.get("week"));
  const week = params.get("week") !== null && isWeek(asked) ? asked : current;
  const setWeek = useCallback(
    (next: number) =>
      setParams((prev) => {
        const out = new URLSearchParams(prev);
        out.set("week", String(next));
        return out;
      }, { replace: true }),
    [setParams],
  );
  return { week, setWeek };
}

/**
 * "Moves · Week 9 · Colgate": the muted line above a page's h1. Pages that ignore ?week= (`followsWeek` false)
 * show the current week, the week their data is for.
 */
export function usePageEyebrow(page: string, followsWeek = false): string {
  const { week } = useWeek();
  const current = useCurrentWeek();
  const { league, leagues } = useLeague();
  const name = leagues.kind === "ready" ? leagues.data.find((l) => l.league_key === league)?.name?.trim() : null;
  return [page, `Week ${followsWeek ? week : current}`, name].filter(Boolean).join(" · ");
}
