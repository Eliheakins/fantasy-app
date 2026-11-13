import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from "react";
import type { League } from "@/api/types";
import type { ApiData, Params, Route } from "@/api/client";
import type { ApiState } from "@/api/envelope";
import { useApiQueries, useApiQuery, useEnvelopeMutation, useEnvelopeQuery } from "@/api/useEnvelope";

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
  const raw = useEnvelopeQuery("/api/leagues");
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

/** The GET routes under /api/leagues/{league}/ whose only path param is the league. */
export type LeagueRoute = {
  [P in Route<"get">]: Params<P, "get"> extends { path: infer Path } ? (keyof Path extends "league" ? P : never) : never;
}[Route<"get">];
/** A league route's query params (the league itself is filled in). */
type LeagueQuery<P extends LeagueRoute> = Params<P, "get">["query"];
type LeagueData<P extends LeagueRoute> = ApiData<P, "get">;

const leagueParams = (league: string, query: object | undefined) => ({
  path: { league },
  query: query as Record<string, unknown> | undefined,
});

/** GET a league route for the selected league; loading until a league is chosen. */
export function useLeagueApi<P extends LeagueRoute>(route: P, query?: LeagueQuery<P>): ApiState<LeagueData<P>> {
  const { league } = useLeague();
  return useApiQuery<LeagueData<P>>(route, league === null ? null : leagueParams(league, query));
}

/** Every league from /api/leagues, independent of the top-bar picker (untrimmed, for per-league blocks). */
export function useAllLeagues(): ApiState<League[]> {
  return useEnvelopeQuery("/api/leagues");
}

/**
 * One GET of a league route per league, whatever the league select says and always for my own team (no `team`):
 * to-dos and visit changes are about my teams. Same query key as `useEnvelopeQuery`, so the cache is shared.
 * A null route turns the queries off.
 */
export function useEachLeague<P extends LeagueRoute>(
  leagueKeys: readonly string[],
  route: P | null,
  query?: LeagueQuery<P>,
): ApiState<LeagueData<P>>[] {
  return useApiQueries<LeagueData<P>>(
    route ?? "",
    leagueKeys.map((key) => (route === null ? null : leagueParams(key, query))),
  );
}

export function useLeagueQuery<P extends LeagueRoute>(leagueKey: string, route: P | null, query?: LeagueQuery<P>): ApiState<LeagueData<P>> {
  return useEachLeague([leagueKey], route, query)[0] ?? { kind: "loading" };
}

/** POST /api/live/refresh, then refetch every GET. */
export const useRefreshScores = () => useEnvelopeMutation("post", "/api/live/refresh", [["api"]]);
