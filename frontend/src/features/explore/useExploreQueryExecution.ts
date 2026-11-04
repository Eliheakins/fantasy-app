import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { browserColumnStore } from "@/shared/engine/parquetColumns";
import { runStatQuery } from "@/shared/engine/statQuery";
import { seasonSources } from "@/shared/lib/dataSources";
import { getFilterChipGroups } from "@/shared/lib/filterChipGroups";
import { createLatestRunner } from "@/shared/lib/latestRun";
import { describeQuery } from "@/shared/lib/queryBuilder";
import type { QueryResult } from "@/shared/types/workbench";
import { useManifestStore } from "@/stores/useManifestStore";
import { useQueryBuilderStore } from "@/stores/useQueryBuilderStore";
import { useWorkbenchStore } from "@/stores/useWorkbenchStore";

export function useExploreQueryExecution() {
  const pinnedPlayers = useWorkbenchStore((s) => s.pinnedPlayers);
  const manifest = useManifestStore((s) => s.manifest);
  const selectedStatIds = useQueryBuilderStore((s) => s.selectedStatIds);
  const activeGranularity = useQueryBuilderStore((s) => s.activeGranularity);
  const minPlays = useQueryBuilderStore((s) => s.minPlays);
  const filterChipState = useQueryBuilderStore((s) => s.filterChipState);

  const sources = useMemo(() => seasonSources(manifest), [manifest]);

  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [details, setDetails] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  // Only the latest run may set state; an older, slower one is aborted and ignored.
  const runLatest = useRef(createLatestRunner()).current;

  const executeQuery = useCallback(async () => {
    setError(null);

    const invalid = (message: string) => {
      runLatest.cancel();
      setRunning(false);
      setResult(null);
      setDetails(null);
      setError(message);
    };

    if (pinnedPlayers.length === 0) {
      invalid("Pin at least one player in The Who, then run again.");
      return;
    }
    if (sources.length === 0) {
      invalid("The data has no seasons yet. Build it with: uv run python backend/scripts/build_data.py");
      return;
    }
    if (selectedStatIds.length === 0) {
      invalid("Select at least one metric.");
      return;
    }

    setRunning(true);
    setDetails(describeQuery({ statIds: selectedStatIds, granularity: activeGranularity, filterChipState, minPlays }));
    let stale = false;
    try {
      const outcome = await runLatest((signal) =>
        runStatQuery(
          {
            statIds: selectedStatIds,
            filterChipState,
            gsisIds: pinnedPlayers.map((p) => p.gsis_id),
            sources,
            granularity: activeGranularity,
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
      setError(null);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (!stale) {
        setRunning(false);
      }
    }
  }, [pinnedPlayers, sources, selectedStatIds, minPlays, filterChipState, activeGranularity, runLatest]);

  useEffect(() => () => runLatest.cancel(), [runLatest]);

  useEffect(() => {
    if (pinnedPlayers.length === 0 || sources.length === 0) {
      // Nothing to show: stop any run still in flight so it cannot land results for players no longer pinned.
      runLatest.cancel();
      setRunning(false);
      setResult(null);
      setDetails(null);
      return;
    }
    if (selectedStatIds.length === 0) {
      runLatest.cancel();
      setRunning(false);
      setResult(null);
      setDetails(null);
      setError(null);
      return;
    }
    void executeQuery();
  }, [activeGranularity, selectedStatIds, minPlays, filterChipState, pinnedPlayers, sources, executeQuery, runLatest]);

  return {
    result,
    error,
    details,
    running,
    executeQuery,
    pinnedPlayers,
  };
}
