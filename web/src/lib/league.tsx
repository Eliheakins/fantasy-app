import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from "react";
import type { League } from "@/api/types";
import { useApi } from "@/hooks/useApi";
import type { ApiState } from "@/api/envelope";

const STORAGE_KEY = "fantasy.league";

function readStored(): string | null {
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

type LeagueContextValue = {
  leagues: ApiState<League[]>;
  /** Selected league_key, or null until the league list has loaded. */
  league: string | null;
  setLeague: (key: string) => void;
};

const LeagueContext = createContext<LeagueContextValue | null>(null);

export function LeagueProvider({ children }: { children: ReactNode }) {
  const leagues = useApi<League[]>("/api/leagues");
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

export function useLeague(): LeagueContextValue {
  const value = useContext(LeagueContext);
  if (!value) throw new Error("useLeague must be used inside LeagueProvider");
  return value;
}

/** GET /api/leagues/{league}/{path} for the selected league; path may carry a query string. */
export function useLeagueApi<T>(path: string): ApiState<T> {
  const { league } = useLeague();
  return useApi<T>(league === null ? null : `/api/leagues/${encodeURIComponent(league)}/${path}`);
}
