import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { browserColumnStore } from "@/stat/engine/parquetColumns";
import { runStatQuery } from "@/stat/engine/statQuery";
import { playerGameSource, playerIndexSource, seasonSources } from "@/stat/lib/dataSources";
import { useFilterChipGroups } from "@/stat/react/filterChipGroups";
import { useManifest } from "@/stat/react/manifest";
import { createLatestRunner } from "@/stat/lib/latestRun";
import { useLeague } from "@/lib/league";
import { useTeam } from "@/lib/teamContext";
import { useLeaguePoints } from "@/stat/react/useLeaguePoints";
import { isLeagueStat } from "@/stat/engine/leaguePointsQuery";
import { playerSetFor, useLeagueOwners } from "@/features/explore/useLeagueOwners";
import { usePinnedPlayers } from "@/features/explore/usePinnedPlayers";
import { isLeagueQuery } from "@/stat/lib/queryUrl";
import { useQueryState } from "@/stat/react/useQueryState";
import { describeQuery } from "@/stat/lib/queryBuilder";
import { queryKey } from "@/stat/lib/queryUrl";
import type { QueryResult } from "@/stat/types/workbench";

/** Runs the query in the URL and keeps its result; only the latest run may set state. */
export function useExploreQueryExecution() {
  const { state, filterChipState, setRoster } = useQueryState();
  const { manifest } = useManifest();
  const chipGroups = useFilterChipGroups();
  const pinnedPlayers = usePinnedPlayers(state.players);

  const sources = useMemo(() => seasonSources(manifest), [manifest]);
  const playerGame = useMemo(() => playerGameSource(manifest), [manifest]);
  const playerIndex = useMemo(() => playerIndexSource(manifest), [manifest]);

  const [result, setResult] = useState<QueryResult | null>(null);
  // Which query the result belongs to: after back/forward the URL changes before the run finishes,
  // and a result must never be shown (or described) as the answer to a different query.
  const [resultKey, setResultKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [details, setDetails] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const runLatest = useRef(createLatestRunner()).current;

  const { players, stats, granularity, minPlays, order, limit, split, subject, teams, side, lastGames, position, rookie } = state;
  const league = isLeagueQuery(state);
  const forTeams = subject === "teams";
  // Whoever the rows are about is named, or the query ranks everyone.
  const { leagues } = useLeague();
  const { league: leagueKey, state: ownersState, byPlayer: owners } = useLeagueOwners();
  // The League filter only applies to player rows, and only once a league is loaded.
  const rosterFilter = !forTeams && leagueKey !== null ? state.roster : null;
  const playerSet = useMemo(
    () => (rosterFilter && owners ? playerSetFor(rosterFilter, [...owners.values()]) : null),
    [rosterFilter, owners],
  );
  // League points come from the fantasy API, one fetch per season. With no season chip only the latest
  // is fetched (a split by season asks for them all); the result says so in a notice.
  const wantsPoints = !forTeams && stats.some(isLeagueStat);
  const { pointSeasons, latestOnly } = useMemo(() => {
    const years = sources.map((s) => s.year);
    const chosen = years.filter((y) => filterChipState[`season-${y}`]);
    if (chosen.length > 0 || split === "season") {
      return { pointSeasons: chosen.length > 0 ? chosen : years, latestOnly: false };
    }
    return { pointSeasons: years.length > 0 ? [Math.max(...years)] : [], latestOnly: true };
  }, [sources, filterChipState, split]);
  const points = useLeaguePoints(wantsPoints ? leagueKey : null, pointSeasons, league ? null : players);
  const pointsRows = points.kind === "ready" ? points.rows : null;
  // The result belongs to the league, viewed team and loaded rosters it was computed for, too.
  const { team } = useTeam();
  const currentKey = useMemo(
    () => `${queryKey(state)}|${leagueKey}|${team}|${playerSet ? "set" : "none"}|${pointsRows ? "pts" : "none"}`,
    [state, leagueKey, team, playerSet, pointsRows],
  );
  // A filter that cannot apply (team rows, or no league at all) would be inert and could not be cleared.
  const inert = state.roster !== null && (forTeams || (leagues.kind === "ready" && leagueKey === null));
  useEffect(() => {
    if (inert) setRoster(null);
  }, [inert, setRoster]);
  const hasSubject = league || (forTeams ? teams.length > 0 : players.length > 0);

  const executeQuery = useCallback(async () => {
    setError(null);

    const invalid = (message: string) => {
      runLatest.cancel();
      setRunning(false);
      setResult(null);
      setDetails(null);
      setError(message);
    };

    if (!hasSubject) {
      invalid(forTeams ? "Pick at least one team in The Who, then run again." : "Pin at least one player in The Who, then run again.");
      return;
    }
    if (sources.length === 0) {
      invalid("The data has no seasons yet. Build it with: make stat-data");
      return;
    }
    if (stats.length === 0) {
      invalid("Select at least one metric.");
      return;
    }

    if ((state.roster || wantsPoints) && !forTeams && leagues.kind === "loading") {
      return; // the league list decides whether the filter or league points apply at all
    }
    if (wantsPoints && leagueKey !== null) {
      if (points.kind === "error") {
        invalid(`League points did not load: ${points.message}`);
        return;
      }
      if (points.kind === "loading") {
        return; // wait for the points rather than show a half-answered query
      }
    }
    if (rosterFilter && !playerSet) {
      // Never show unrestricted rows as the answer to a restricted query: wait for the league's rosters.
      if (ownersState.kind === "error") {
        invalid("The league's rosters did not load, so the League filter cannot apply. Try again or pick All players.");
      }
      return;
    }

    setRunning(true);
    setDetails(describeQuery({ statIds: stats, granularity, filterChipState, chipGroups, minPlays, lastGames, position, rookie }));
    let stale = false;
    try {
      const outcome = await runLatest((signal) =>
        runStatQuery(
          {
            statIds: stats,
            filterChipState,
            gsisIds: league ? null : players,
            playerSet,
            sources,
            playerGame,
            leaguePoints: pointsRows,
            granularity,
            minPlays,
            order,
            limit,
            split,
            teams: forTeams ? { ids: league ? null : teams, side } : null,
            lastGames,
            position,
            rookie,
            playerIndex,
            chipGroups,
          },
          browserColumnStore,
          signal,
        ),
      );
      if (outcome.stale) {
        stale = true;
        return;
      }
      setResult(
        wantsPoints && latestOnly
          ? {
              ...outcome.value,
              notices: [
                ...(outcome.value.notices ?? []),
                `League points cover only the latest season (${pointSeasons[0]}) because no season is picked. Pick seasons to see more.`,
              ],
            }
          : outcome.value,
      );
      setResultKey(currentKey);
      setError(null);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (!stale) {
        setRunning(false);
      }
    }
  }, [
    players,
    league,
    hasSubject,
    forTeams,
    teams,
    side,
    order,
    limit,
    lastGames,
    position,
    rookie,
    playerIndex,
    split,
    sources,
    playerGame,
    stats,
    minPlays,
    filterChipState,
    chipGroups,
    granularity,
    rosterFilter,
    playerSet,
    pointsRows,
    wantsPoints,
    latestOnly,
    pointSeasons,
    leagueKey,
    points,
    state.roster,
    leagues.kind,
    ownersState.kind,
    runLatest,
    currentKey,
  ]);

  useEffect(() => () => runLatest.cancel(), [runLatest]);

  useEffect(() => {
    if (!hasSubject || sources.length === 0) {
      // Nothing to show: stop any run still in flight so it cannot land results for players no longer pinned.
      runLatest.cancel();
      setRunning(false);
      setResult(null);
      setDetails(null);
      return;
    }
    if (stats.length === 0) {
      runLatest.cancel();
      setRunning(false);
      setResult(null);
      setDetails(null);
      setError(null);
      return;
    }
    void executeQuery();
  }, [hasSubject, stats, sources, executeQuery, runLatest]);

  // Names for every row shown: the pinned players, or the players a leaderboard ranked.
  const shown = resultKey === currentKey ? result : null;
  const rowPlayers = usePinnedPlayers(league && !forTeams ? (shown?.rows ?? []).map((r) => String(r.player_id)) : []);

  return {
    result: shown,
    error,
    details,
    running,
    executeQuery,
    pinnedPlayers,
    /** Everyone the table names: pinned players, and for a leaderboard the players it ranked. */
    namedPlayers: [...pinnedPlayers, ...rowPlayers],
  };
}
