import { type ReactNode, useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useApi } from "@/hooks/useApi";
import { useLeague } from "@/lib/league";
import { parseTeam } from "@/lib/team";
import { TeamContext, type TeamContextValue, type TeamRow } from "@/lib/teamContext";

/** Team selection lives in the URL (`?team=<roster_id>&league=<key>`), so a link opens that view.
 * Mount inside the router and LeagueProvider. */
export function TeamProvider({ children }: { children: ReactNode }) {
  const { league } = useLeague();
  const [params, setParams] = useSearchParams();
  const asked = parseTeam(params.get("team"));
  const list = useApi<TeamRow[]>(league === null ? null : `/api/leagues/${encodeURIComponent(league)}/teams`);
  const teams = list.kind === "ready" ? list.data : [];
  const row = teams.find((t) => t.roster_id === asked) ?? null;
  // Until the list loads, trust the URL; once it has, an unknown or own team means the default.
  const team = list.kind !== "ready" || (row !== null && !row.is_me) ? asked : null;
  const setTeam = useCallback(
    (rosterId: number | null) =>
      setParams((prev) => {
        const next = new URLSearchParams(prev);
        if (rosterId === null) {
          next.delete("team");
          next.delete("league");
        } else {
          next.set("team", String(rosterId));
          if (league !== null) next.set("league", league); // makes the link portable
        }
        return next;
      }),
    [setParams, league],
  );
  const value = useMemo<TeamContextValue>(
    () => ({ team, league, teams, viewed: team === null ? null : row, setTeam }),
    [team, league, teams, row, setTeam],
  );
  return <TeamContext.Provider value={value}>{children}</TeamContext.Provider>;
}
