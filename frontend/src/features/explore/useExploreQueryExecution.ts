import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { browserColumnStore } from "@/shared/engine/parquetColumns";
import { runStatQuery } from "@/shared/engine/statQuery";
import { seasonSources } from "@/shared/lib/dataSources";
import { getFilterChipGroups } from "@/shared/lib/filterChipGroups";
import { createLatestRunner } from "@/shared/lib/latestRun";
import { usePinnedPlayers } from "@/shared/lib/usePinnedPlayers";
import { useQueryState } from "@/shared/lib/useQueryState";
import { describeQuery } from "@/shared/lib/queryBuilder";
import { queryKey } from "@/shared/lib/queryUrl";
import type { QueryResult } from "@/shared/types/workbench";
import { useManifestStore } from "@/stores/useManifestStore";

/** Runs the query in the URL and keeps its result; only the latest run may set state. */
export function useExploreQueryExecution() {
  const { state, filterChipState } = useQueryState();
  const manifest = useManifestStore((s) => s.manifest);
  const pinnedPlayers = usePinnedPlayers(state.players);

  const sources = useMemo(() => seasonSources(manifest), [manifest]);

  const [result, setResult] = useState<QueryResult | null>(null);
  // Which query the result belongs to: after back/forward the URL changes before the run finishes,
  // and a result must never be shown (or described) as the answer to a different query.
  const [resultKey, setResultKey] = useState<string | null>(null);
  const currentKey = useMemo(() => queryKey(state), [state]);
  const [error, setError] = useState<string | null>(null);
  const [details, setDetails] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const runLatest = useRef(createLatestRunner()).current;

  const { players, stats, granularity, minPlays } = state;

  const executeQuery = useCallback(async () => {
    setError(null);

    const invalid = (message: string) => {
      runLatest.cancel();
      setRunning(false);
      setResult(null);
      setDetails(null);
      setError(message);
    };

    if (players.length === 0) {
      invalid("Pin at least one player in The Who, then run again.");
      return;
    }
    if (sources.length === 0) {
      invalid("The data has no seasons yet. Build it with: uv run python backend/scripts/build_data.py");
      return;
    }
    if (stats.length === 0) {
      invalid("Select at least one metric.");
      return;
    }

    setRunning(true);
    setDetails(describeQuery({ statIds: stats, granularity, filterChipState, minPlays }));
    let stale = false;
    try {
      const outcome = await runLatest((signal) =>
        runStatQuery(
          {
            statIds: stats,
            filterChipState,
            gsisIds: players,
            sources,
            granularity,
            minPlays,
            chipGroups: getFilterChipGroups(),
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
  }, [players, sources, stats, minPlays, filterChipState, granularity, runLatest, currentKey]);

  useEffect(() => () => runLatest.cancel(), [runLatest]);

  useEffect(() => {
    if (players.length === 0 || sources.length === 0) {
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
  }, [players, stats, sources, executeQuery, runLatest]);

  return {
    result: resultKey === currentKey ? result : null,
    error,
    details,
    running,
    executeQuery,
    pinnedPlayers,
  };
}
