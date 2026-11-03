import { useCallback, useEffect, useMemo, useState } from "react";

import {
  buildStatQueryPlans,
  mergeStatQueryResults,
} from "@/shared/lib/queryBuilderSql";
import { runQuery } from "@/shared/lib/duckdb";
import { ensurePbpMounted } from "@/shared/lib/workbenchDuckdb";
import { mergeShardMap } from "@/shared/lib/mergeShards";
import { shardParquetUrl } from "@/shared/lib/api";
import type { QueryResult } from "@/shared/types/workbench";
import { useQueryBuilderStore } from "@/stores/useQueryBuilderStore";
import { useWorkbenchStore } from "@/stores/useWorkbenchStore";

export function useExploreQueryExecution() {
  const pinnedPlayers = useWorkbenchStore((s) => s.pinnedPlayers);
  const playerShardMap = useWorkbenchStore((s) => s.playerShardMap);
  const selectedStatIds = useQueryBuilderStore((s) => s.selectedStatIds);
  const activeGranularity = useQueryBuilderStore((s) => s.activeGranularity);
  const minPlays = useQueryBuilderStore((s) => s.minPlays);
  const filterChipState = useQueryBuilderStore((s) => s.filterChipState);

  const shards = useMemo(() => mergeShardMap(playerShardMap), [playerShardMap]);
  const viewNames = useMemo(() => shards.map((s) => `nfl_pbp_${s.year}`), [shards]);

  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastSql, setLastSql] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const executeQuery = useCallback(async () => {
    setError(null);

    if (pinnedPlayers.length === 0) {
      setResult(null);
      setLastSql(null);
      setError("Pin at least one player in The Who, then run again.");
      return;
    }
    if (shards.length === 0) {
      setResult(null);
      setLastSql(null);
      setError("No Parquet shards found for pinned players. Check the API and data folder.");
      return;
    }
    if (selectedStatIds.length === 0) {
      setResult(null);
      setLastSql(null);
      setError("Select at least one metric.");
      return;
    }

    let plans: ReturnType<typeof buildStatQueryPlans>;
    try {
      plans = buildStatQueryPlans({
        statIds: selectedStatIds,
        filterChipState,
        gsisIds: pinnedPlayers.map((p) => p.gsis_id),
        viewNames,
        granularity: activeGranularity,
        minPlays,
      });
    } catch (e) {
      setResult(null);
      setLastSql(null);
      setError(e instanceof Error ? e.message : String(e));
      return;
    }

    setRunning(true);
    setLastSql(plans.map((p) => p.sql).join("\n\n-- —— next query ——\n\n"));
    try {
      await ensurePbpMounted(shards, shardParquetUrl);
      const rawResults: QueryResult[] = [];
      for (const plan of plans) {
        rawResults.push(await runQuery(plan.sql));
      }
      const merged = mergeStatQueryResults(rawResults, selectedStatIds);
      setResult(merged);
      setError(null);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }, [
    pinnedPlayers,
    shards,
    selectedStatIds,
    minPlays,
    filterChipState,
    viewNames,
    activeGranularity,
  ]);

  useEffect(() => {
    if (pinnedPlayers.length === 0 || shards.length === 0) {
      return;
    }
    if (selectedStatIds.length === 0) {
      setResult(null);
      setLastSql(null);
      setError(null);
      return;
    }
    void executeQuery();
  }, [
    activeGranularity,
    selectedStatIds,
    minPlays,
    filterChipState,
    pinnedPlayers,
    shards,
    executeQuery,
  ]);

  return {
    result,
    error,
    lastSql,
    running,
    executeQuery,
    pinnedPlayers,
  };
}
