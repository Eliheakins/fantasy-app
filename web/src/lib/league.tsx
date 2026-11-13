import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from "react";
import type { League } from "@/api/types";
import { useEnvelopeMutation, useEnvelopeQueries, useEnvelopeQuery } from "@/api/useEnvelope";
import type { ApiState } from "@/api/envelope";

const STORAGE_KEY = "fantasy.league";

function readStored(): string | null {
  const linked = new URLSearchParams(window.location.search).get("league"); // a shared link wins
  if (linked) return linked;
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function store(key: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, key);
  } catch {
    // Storage can be blocked; the picker still works for this visit.
  }
}

/** Sleeper pads some league names with a trailing space; trim for display. */
export function trimLeagueNames(state: ApiState<League[]>): ApiState<League[]> {
  if (state.kind !== "ready") return state;
  return { ...state, data: state.data.map((l) => ({ ...l, name: l.name?.trim() ?? l.name })) };
}

type LeagueContextValue = {
  leagues: ApiState<League[]>;
  /** Selected league_key, or null until the league list has loaded. */
  league: string | null;
  setLeague: (key: string) => void;
};

const LeagueContext = createContext<LeagueContextValue | null>(null);

export function LeagueProvider({ children }: { children: ReactNode }) {
  const raw = useEnvelopeQuery<League[]>("/api/leagues");
  const leagues = useMemo(() => trimLeagueNames(raw), [raw]);
  const [chosen, setChosen] = useState<string | null>(readStored);
  const setLeague = useCallback((key: string) => {
    setChosen(key);
    store(key);
  }, []);
  const value = useMemo<LeagueContextValue>(() => {
    const list = leagues.kind === "ready" ? leagues.data : [];
    const valid = list.some((l) => l.league_key === chosen);
    return { leagues, league: valid ? chosen : (list[0]?.league_key ?? null), setLeague };
  }, [leagues, chosen, setLeague]);
  return <LeagueContext.Provider value={value}>{children}</LeagueContext.Provider>;
}

/** The selected league's row, or undefined with no provider, no league or the list not loaded. */
export function useLeagueRow(): League | undefined {
  const value = useContext(LeagueContext);
  if (!value || value.league === null || value.leagues.kind !== "ready") return undefined;
  return value.leagues.data.find((l) => l.league_key === value.league);
}

/** The selected league's display name, or null with no provider, no league or the list not loaded. */
export const useLeagueName = (): string | null => useLeagueRow()?.name ?? null;

/** The selected league's playoff size; 6 (the app's usual league) until the list has loaded. */
export const usePlayoffTeams = (): number => useLeagueRow()?.playoff_teams ?? 6;

export function useLeague(): LeagueContextValue {
  const value = useContext(LeagueContext);
  if (!value) throw new Error("useLeague must be used inside LeagueProvider");
  return value;
}

export const leagueUrl = (key: string, path: string) => `/api/leagues/${encodeURIComponent(key)}/${path}`;

/** GET /api/leagues/{league}/{path} for the selected league; path may carry a query string. */
export function useLeagueApi<T>(path: string): ApiState<T> {
  const { league } = useLeague();
  return useEnvelopeQuery<T>(league === null ? null : leagueUrl(league, path));
}

/** Every league from /api/leagues, independent of the top-bar picker (untrimmed, for per-league blocks). */
export function useAllLeagues(): ApiState<League[]> {
  return useEnvelopeQuery<League[]>("/api/leagues");
}

/**
 * One GET per league, whatever the league select says and always for my own team (no `?team=`):
 * to-dos and visit changes are about my teams. Same query key as `useEnvelopeQuery`, so the cache is shared.
 * A null path turns the queries off.
 */
export function useEachLeague<T>(leagueKeys: readonly string[], path: string | null): ApiState<T>[] {
  return useEnvelopeQueries<T>(leagueKeys.map((key) => (path === null ? null : leagueUrl(key, path))));
}

export function useLeagueQuery<T>(leagueKey: string, path: string | null): ApiState<T> {
  return useEachLeague<T>([leagueKey], path)[0] ?? { kind: "loading" };
}

/** POST /api/live/refresh, then refetch everything. */
export const useRefreshScores = () => useEnvelopeMutation<{ player_rows: number }>("/api/live/refresh");
