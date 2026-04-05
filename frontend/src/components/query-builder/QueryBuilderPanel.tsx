import { useCallback, useEffect, useMemo, useState } from "react";

import { FilterChipsBar } from "@/components/query-builder/FilterChipsBar";
import { GranularitySelector } from "@/components/query-builder/GranularitySelector";
import { MinPlaysSlider } from "@/components/query-builder/MinPlaysSlider";
import { PinnedPlayersBar } from "@/components/query-builder/PinnedPlayersBar";
import {
  buildScatterPoints,
  StatScatterChart,
} from "@/components/query-builder/StatScatterChart";
import { StatDictionaryPanel } from "@/components/query-builder/StatDictionaryPanel";
import { getStatById } from "@/config/statDictionary";
import { shardParquetUrl } from "@/lib/api";
import { initDB, mountRemoteShard, runQuery } from "@/lib/duckdb";
import { mergeShardMap } from "@/lib/mergeShards";
import {
  buildStatQueryPlans,
  formatMetricValueHeader,
  mergeStatQueryResults,
  metricSelectAlias,
} from "@/lib/queryBuilderSql";
import type { QueryResult } from "@/types/workbench";
import { useQueryBuilderStore } from "@/store/useQueryBuilderStore";
import { useWorkbenchStore } from "@/store/useWorkbenchStore";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

/**
 * Guided query UI: Who (pinned) → What (stats, up to 5) + canvas → Granularity → Min plays → Context (chips) → Run.
 */
export function QueryBuilderPanel() {
  const pinnedPlayers = useWorkbenchStore((s) => s.pinnedPlayers);
  const playerShardMap = useWorkbenchStore((s) => s.playerShardMap);
  const selectedStatIds = useQueryBuilderStore((s) => s.selectedStatIds);
  const activeGranularity = useQueryBuilderStore((s) => s.activeGranularity);
  const minPlays = useQueryBuilderStore((s) => s.minPlays);
  const filterChipState = useQueryBuilderStore((s) => s.filterChipState);

  const shards = useMemo(() => mergeShardMap(playerShardMap), [playerShardMap]);
  const viewNames = useMemo(() => shards.map((s) => `nfl_pbp_${s.year}`), [shards]);

  const columnHeaders = useMemo(() => {
    const headers = new Map<string, string>();
    for (const id of selectedStatIds) {
      const st = getStatById(id);
      headers.set(metricSelectAlias(id), formatMetricValueHeader(st, activeGranularity));
    }
    return headers;
  }, [selectedStatIds, activeGranularity]);

  const nameByGsis = useMemo(() => {
    const m = new Map<string, string>();
    for (const p of pinnedPlayers) {
      m.set(p.gsis_id, p.full_name ?? p.gsis_id);
    }
    return m;
  }, [pinnedPlayers]);

  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastSql, setLastSql] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [canvasView, setCanvasView] = useState<"table" | "scatter">("table");
  const [swapScatterAxes, setSwapScatterAxes] = useState(false);

  const twoStatsMode = selectedStatIds.length === 2;

  useEffect(() => {
    if (!twoStatsMode) {
      setCanvasView("table");
      setSwapScatterAxes(false);
    }
  }, [twoStatsMode]);

  const scatterPoints = useMemo(() => {
    if (!result || !twoStatsMode) {
      return [];
    }
    const [a, b] = selectedStatIds;
    const xId = swapScatterAxes ? b! : a!;
    const yId = swapScatterAxes ? a! : b!;
    const xCol = metricSelectAlias(xId);
    const yCol = metricSelectAlias(yId);
    return buildScatterPoints(
      result.rows as Record<string, unknown>[],
      xCol,
      yCol,
      nameByGsis,
    );
  }, [result, twoStatsMode, selectedStatIds, swapScatterAxes, nameByGsis]);

  const scatterXLabel = useMemo(() => {
    if (!twoStatsMode) {
      return "";
    }
    const xId = swapScatterAxes ? selectedStatIds[1]! : selectedStatIds[0]!;
    const st = getStatById(xId);
    return columnHeaders.get(metricSelectAlias(xId)) ?? formatMetricValueHeader(st, activeGranularity);
  }, [twoStatsMode, swapScatterAxes, selectedStatIds, columnHeaders, activeGranularity]);

  const scatterYLabel = useMemo(() => {
    if (!twoStatsMode) {
      return "";
    }
    const yId = swapScatterAxes ? selectedStatIds[0]! : selectedStatIds[1]!;
    const st = getStatById(yId);
    return columnHeaders.get(metricSelectAlias(yId)) ?? formatMetricValueHeader(st, activeGranularity);
  }, [twoStatsMode, swapScatterAxes, selectedStatIds, columnHeaders, activeGranularity]);

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
      await initDB();
      for (const s of shards) {
        const url = shardParquetUrl(s.path);
        await mountRemoteShard(url, `nfl_pbp_${s.year}`);
      }
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

  return (
    <div className="flex flex-col gap-4">
      <PinnedPlayersBar />

      <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
        <StatDictionaryPanel className="lg:max-w-xs lg:shrink-0" />
        <Card className="min-h-[160px] flex-1 border-zinc-800 bg-zinc-950/60">
          <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 pb-2">
            <CardTitle className="text-base text-zinc-300">Canvas</CardTitle>
            {twoStatsMode && result && result.rows.length > 0 ? (
              <div className="flex flex-wrap items-center gap-2">
                <ToggleGroup
                  type="single"
                  value={canvasView}
                  onValueChange={(v) => {
                    if (v === "table" || v === "scatter") {
                      setCanvasView(v);
                    }
                  }}
                  size="sm"
                  className="justify-end"
                >
                  <ToggleGroupItem value="table" aria-label="Table view">
                    Table
                  </ToggleGroupItem>
                  <ToggleGroupItem value="scatter" aria-label="X Y scatter chart">
                    X / Y chart
                  </ToggleGroupItem>
                </ToggleGroup>
                {canvasView === "scatter" ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-8 border-zinc-700 bg-zinc-900/50 text-xs text-zinc-300"
                    onClick={() => setSwapScatterAxes((s) => !s)}
                  >
                    Swap axes
                  </Button>
                ) : null}
              </div>
            ) : null}
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {running && <p className="text-xs text-zinc-500">Updating…</p>}
            {error && (
              <div className="rounded-md border border-red-900/60 bg-red-950/35 px-3 py-2 text-red-200">{error}</div>
            )}

            {result && result.rows.length > 0 ? (
              canvasView === "scatter" && twoStatsMode ? (
                <div className="flex justify-center overflow-x-auto rounded-md border border-zinc-800 bg-zinc-900/30 py-4">
                  <StatScatterChart
                    points={scatterPoints}
                    xLabel={scatterXLabel}
                    yLabel={scatterYLabel}
                  />
                </div>
              ) : (
                <div className="overflow-x-auto rounded-md border border-zinc-800">
                  <table className="w-full border-collapse text-left text-sm">
                    <thead>
                      <tr className="border-b border-zinc-800 bg-zinc-900/80">
                        <th className="px-3 py-2 font-medium text-zinc-400">Player</th>
                        {result.columns
                          .filter((col) => col !== "player_id")
                          .map((col) => (
                            <th key={col} className="px-3 py-2 font-medium text-zinc-400">
                              {columnHeaders.get(col) ?? col}
                            </th>
                          ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.rows.map((row, i) => {
                        const pid = String(row.player_id ?? "");
                        const label = nameByGsis.get(pid) ?? pid;
                        return (
                          <tr key={`${pid}-${i}`} className="border-b border-zinc-800/80 last:border-0">
                            <td className="px-3 py-2 font-medium text-zinc-200">{label}</td>
                            {result.columns
                              .filter((col) => col !== "player_id")
                              .map((col) => (
                                <td key={col} className="px-3 py-2 font-mono text-zinc-300">
                                  {formatCell(row[col])}
                                </td>
                              ))}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )
            ) : result && result.rows.length === 0 && !running ? (
              <p className="text-zinc-500">Query returned no rows for this combination of filters.</p>
            ) : !error && !running && pinnedPlayers.length === 0 ? (
              <p className="text-zinc-500">
                Pin players to load data. Stats, granularity, min plays, and filter changes refresh the table
                automatically.
              </p>
            ) : !error && !running && pinnedPlayers.length > 0 && selectedStatIds.length === 0 ? (
              <p className="text-zinc-500">Select at least one metric in The What to load the canvas.</p>
            ) : null}

            {lastSql && (
              <details className="text-xs text-zinc-600">
                <summary className="cursor-pointer text-zinc-500 hover:text-zinc-400">Last SQL</summary>
                <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-zinc-900/80 p-2 font-mono text-[11px] text-zinc-400">
                  {lastSql}
                </pre>
              </details>
            )}
          </CardContent>
        </Card>
      </div>

      <GranularitySelector />

      <MinPlaysSlider />

      <FilterChipsBar />

      <div className="flex flex-wrap items-center justify-end gap-2 border-t border-zinc-800/80 pt-2">
        <Button type="button" onClick={() => void executeQuery()} disabled={running}>
          {running ? "Running…" : "Run"}
        </Button>
      </div>
    </div>
  );
}

function formatCell(v: unknown): string {
  if (v === null || v === undefined) {
    return "—";
  }
  if (typeof v === "number" && !Number.isInteger(v)) {
    return v.toFixed(4);
  }
  return String(v);
}
