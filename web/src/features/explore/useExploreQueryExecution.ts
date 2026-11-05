import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { browserColumnStore } from "@/stat/engine/parquetColumns";
import { runStatQuery } from "@/stat/engine/statQuery";
import { playerGameSource, seasonSources } from "@/stat/lib/dataSources";
import { useFilterChipGroups } from "@/features/explore/filterChipGroups";
import { useManifest } from "@/features/explore/manifest";
import { createLatestRunner } from "@/stat/lib/latestRun";
import { usePinnedPlayers } from "@/features/explore/usePinnedPlayers";
import { isLeagueQuery } from "@/stat/lib/queryUrl";
import { useQueryState } from "@/features/explore/useQueryState";
import { describeQuery } from "@/stat/lib/queryBuilder";
import { queryKey } from "@/stat/lib/queryUrl";
import type { QueryResult } from "@/stat/types/workbench";

/** Runs the query in the URL and keeps its result; only the latest run may set state. */
export function useExploreQueryExecution() {
  const { state, filterChipState } = useQueryState();
  const { manifest } = useManifest();
  const chipGroups = useFilterChipGroups();
  const pinnedPlayers = usePinnedPlayers(state.players);

  const sources = useMemo(() => seasonSources(manifest), [manifest]);
  const playerGame = useMemo(() => playerGameSource(manifest), [manifest]);

  const [result, setResult] = useState<QueryResult | null>(null);
  // Which query the result belongs to: after back/forward the URL changes before the run finishes,
  // and a result must never be shown (or described) as the answer to a different query.
  const [resultKey, setResultKey] = useState<string | null>(null);
  const currentKey = useMemo(() => queryKey(state), [state]);
  const [error, setError] = useState<string | null>(null);
  const [details, setDetails] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const runLatest = useRef(createLatestRunner()).current;

  const { players, stats, granularity, minPlays, order, limit, split, subject, teams, side } = state;
  const league = isLeagueQuery(state);
  const forTeams = subject === "teams";
  // Whoever the rows are about is named, or the query ranks everyone.
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
      invalid(
        forTeams
          ? "Pick at least one team in The Who, then run again."
          : "Pin at least one player in The Who, then run again.",
      );
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

    setRunning(true);
    setDetails(describeQuery({ statIds: stats, granularity, filterChipState, chipGroups, minPlays }));
    let stale = false;
    try {
      const outcome = await runLatest((signal) =>
        runStatQuery(
          {
            statIds: stats,
            filterChipState,
            gsisIds: league ? null : players,
            sources,
            playerGame,
            granularity,
            minPlays,
            order,
            limit,
            split,
            teams: forTeams ? { ids: league ? null : teams, side } : null,
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
      setResult(outcome.value);
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
    split,
    sources,
    playerGame,
    stats,
    minPlays,
    filterChipState,
    chipGroups,
    granularity,
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
