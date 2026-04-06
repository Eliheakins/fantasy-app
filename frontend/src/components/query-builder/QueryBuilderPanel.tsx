import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import {
  QueryBuilderSidebarExecuteFooter,
  QueryBuilderSidebarScroll,
} from "@/components/query-builder/QueryBuilderSidebarBody";
import {
  buildScatterPoints,
  StatScatterChart,
} from "@/components/query-builder/StatScatterChart";
import { getStatById } from "@/config/statDictionary";
import { fetchPlayerDetail, searchPlayers, shardParquetUrl } from "@/lib/api";
import { initDB, mountRemoteShard, runQuery } from "@/lib/duckdb";
import { mergeShardMap } from "@/lib/mergeShards";
import {
  buildStatQueryPlans,
  formatMetricValueHeader,
  mergeStatQueryResults,
  metricSelectAlias,
} from "@/lib/queryBuilderSql";
import type { NFLPlayer, QueryResult } from "@/types/workbench";
import { useQueryBuilderStore } from "@/store/useQueryBuilderStore";
import { MAX_PINNED_PLAYERS, useWorkbenchStore } from "@/store/useWorkbenchStore";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";
import { Drawer } from "vaul";

interface QueryBuilderPanelProps {
  children?: ReactNode;
}

/** Mobile sheet snap heights as a fraction of the viewport (Vaul: e.g. 0.5 = 50%, not 50). */
const MOBILE_BUILDER_SNAP_POINTS: (number | string)[] = [0.5, 1];

/**
 * Guided query UI: sidebar (who / what / context) + main canvas + optional children (e.g. Formula Lab).
 */
export function QueryBuilderPanel({ children }: QueryBuilderPanelProps) {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [pinMessage, setPinMessage] = useState<string | null>(null);

  const pinnedPlayers = useWorkbenchStore((s) => s.pinnedPlayers);
  const tryPinPlayer = useWorkbenchStore((s) => s.tryPinPlayer);
  const playerShardMap = useWorkbenchStore((s) => s.playerShardMap);
  const selectedStatIds = useQueryBuilderStore((s) => s.selectedStatIds);
  const activeGranularity = useQueryBuilderStore((s) => s.activeGranularity);
  const minPlays = useQueryBuilderStore((s) => s.minPlays);
  const filterChipState = useQueryBuilderStore((s) => s.filterChipState);

  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(query), 250);
    return () => window.clearTimeout(t);
  }, [query]);

  const searchQ = useQuery({
    queryKey: ["search", debounced],
    queryFn: () => searchPlayers(debounced),
    enabled: debounced.trim().length >= 2,
  });

  const onSelectPlayer = useCallback(
    async (p: NFLPlayer) => {
      setPinMessage(null);
      if (pinnedPlayers.some((x) => x.gsis_id === p.gsis_id)) {
        setPinMessage("Already pinned.");
        return;
      }
      if (pinnedPlayers.length >= MAX_PINNED_PLAYERS) {
        setPinMessage(`You can pin at most ${MAX_PINNED_PLAYERS} players.`);
        return;
      }

      try {
        const d = await fetchPlayerDetail(p.gsis_id);
        const ok = tryPinPlayer(p, d.shards);
        if (ok) {
          setQuery("");
        } else {
          setPinMessage("Could not pin (duplicate or limit).");
        }
      } catch (e) {
        setPinMessage(e instanceof Error ? e.message : String(e));
      }
    },
    [pinnedPlayers, tryPinPlayer],
  );

  const suggestions = useMemo(() => searchQ.data ?? [], [searchQ.data]);

  const isPinned = useCallback(
    (gsisId: string) => pinnedPlayers.some((p) => p.gsis_id === gsisId),
    [pinnedPlayers],
  );

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
  const [mobileBuilderOpen, setMobileBuilderOpen] = useState(false);
  /** Vaul snap: default half viewport; user can drag to full height. */
  const [mobileActiveSnap, setMobileActiveSnap] = useState<number | string | null>(0.5);

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

  const canvasSubtitle = useMemo(() => {
    if (selectedStatIds.length === 0) {
      return "Select metrics in the query builder to populate results.";
    }
    const labels = selectedStatIds
      .map((id) => getStatById(id))
      .filter(Boolean)
      .map((s) => s!.label);
    const gran =
      activeGranularity === "total" ? "totals" : activeGranularity === "per_game" ? "per game" : "per play";
    return `${labels.join(" · ")} · ${gran} · min ${minPlays} plays`;
  }, [selectedStatIds, activeGranularity, minPlays]);

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

  const sidebarScrollProps = {
    query,
    setQuery,
    debounced,
    suggestions,
    isPinned,
    pinnedPlayers,
    onSelectPlayer,
    pinMessage,
  };

  const onExecute = () => void executeQuery();

  return (
    <>
      <div className="flex min-h-dvh flex-col bg-app lg:min-h-screen lg:flex-row">
        <aside className="hidden w-full shrink-0 flex-col border-border bg-surface lg:flex lg:sticky lg:top-0 lg:h-screen lg:w-[360px] lg:border-r">
          <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto p-5">
            <QueryBuilderSidebarScroll {...sidebarScrollProps} />
          </div>
          <QueryBuilderSidebarExecuteFooter running={running} onExecute={onExecute} />
        </aside>

        <main className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 pb-28 pt-4 lg:space-y-6 lg:p-8 lg:pb-8">
          <header className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-widest text-accent-muted">Workbench / Query</p>
            <h2 className="text-xl font-bold tracking-tight text-ink lg:text-2xl">The Bridge</h2>
            <p className="max-w-2xl text-xs text-ink-muted lg:text-sm">
              Football data workbench · Parquet in the browser. Results below — on phones, tap the{" "}
              <span className="lg:hidden">filter button</span>
              <span className="hidden lg:inline">query builder</span> to pick players, metrics, and filters. Formula Lab
              runs custom SQL on the same pinned shards.
            </p>
          </header>

        <Card className="min-h-[160px] overflow-hidden">
          <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2 pb-2">
            <div>
              <CardTitle className="text-base text-ink">Results canvas</CardTitle>
              <p className="mt-1 text-xs text-ink-muted">{canvasSubtitle}</p>
            </div>
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
                    className="h-8 text-xs"
                    onClick={() => setSwapScatterAxes((s) => !s)}
                  >
                    Swap axes
                  </Button>
                ) : null}
              </div>
            ) : null}
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {running && <p className="text-xs text-ink-muted">Updating…</p>}
            {error && (
              <div className="rounded-md border border-danger/25 bg-danger/5 px-3 py-2 text-sm text-danger-fg">
                {error}
              </div>
            )}

            {result && result.rows.length > 0 ? (
              canvasView === "scatter" && twoStatsMode ? (
                <div className="flex justify-center overflow-x-auto rounded-md border border-border bg-input/40 py-4">
                  <StatScatterChart
                    points={scatterPoints}
                    xLabel={scatterXLabel}
                    yLabel={scatterYLabel}
                  />
                </div>
              ) : (
                <div className="overflow-x-auto rounded-md border border-border">
                  <table className="w-full border-collapse text-left text-sm">
                    <thead>
                      <tr className="border-b border-border bg-input/60">
                        <th className="px-3 py-2 font-medium text-ink-muted">Player</th>
                        {result.columns
                          .filter((col) => col !== "player_id")
                          .map((col) => (
                            <th key={col} className="px-3 py-2 font-medium text-ink-muted">
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
                          <tr key={`${pid}-${i}`} className="border-b border-border/80 last:border-0">
                            <td className="px-3 py-2 font-medium text-ink">{label}</td>
                            {result.columns
                              .filter((col) => col !== "player_id")
                              .map((col) => (
                                <td key={col} className="px-3 py-2 font-mono text-accent">
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
              <p className="text-ink-muted">Query returned no rows for this combination of filters.</p>
            ) : !error && !running && pinnedPlayers.length === 0 ? (
              <p className="text-ink-muted">
                <span className="lg:hidden">Open the query builder (bottom-right) to search and pin players. </span>
                <span className="hidden lg:inline">Pin players to load data. </span>
                Stats, granularity, min plays, and filter changes refresh the table automatically.
              </p>
            ) : !error && !running && pinnedPlayers.length > 0 && selectedStatIds.length === 0 ? (
              <p className="text-ink-muted">
                <span className="lg:hidden">Open the query builder and pick metrics under The What. </span>
                <span className="hidden lg:inline">Select at least one metric in The What to load the canvas.</span>
              </p>
            ) : null}

            {lastSql && (
              <details className="text-xs text-ink-muted">
                <summary className="cursor-pointer hover:text-ink">Last SQL</summary>
                <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded border border-border bg-input p-2 font-mono text-[11px] text-ink-muted">
                  {lastSql}
                </pre>
              </details>
            )}
          </CardContent>
        </Card>

        {children ? <div className="space-y-2">{children}</div> : null}
      </main>
      </div>

      <button
        type="button"
        onClick={() => {
          setMobileActiveSnap(0.5);
          setMobileBuilderOpen(true);
        }}
        className={cn(
          "fixed z-[70] flex h-14 w-14 items-center justify-center rounded-full bg-primary text-surface shadow-lg lg:hidden",
          "transition hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-app",
          "bottom-[max(1.25rem,env(safe-area-inset-bottom,0px))] right-4",
          mobileBuilderOpen && "hidden",
        )}
        aria-label="Open query builder"
        aria-expanded={mobileBuilderOpen}
        aria-haspopup="dialog"
        tabIndex={mobileBuilderOpen ? -1 : undefined}
      >
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
          <path d="M3 6h18M7 12h10M11 18h2" strokeLinecap="round" />
        </svg>
      </button>

      <Drawer.Root
        open={mobileBuilderOpen}
        onOpenChange={(open) => {
          setMobileBuilderOpen(open);
          setMobileActiveSnap(0.5);
        }}
        snapPoints={MOBILE_BUILDER_SNAP_POINTS}
        activeSnapPoint={mobileActiveSnap}
        setActiveSnapPoint={setMobileActiveSnap}
        modal
        shouldScaleBackground={false}
        dismissible
        noBodyStyles
        autoFocus
      >
        <Drawer.Portal>
          <Drawer.Overlay className="fixed inset-0 z-[65] bg-ink/40 backdrop-blur-[1px]" />
          <Drawer.Content
            className={cn(
              "fixed inset-x-0 bottom-0 z-[66] flex max-h-[100dvh] flex-col rounded-t-2xl border-x border-t border-border bg-surface shadow-[0_-8px_30px_rgb(15_23_42/0.12)] outline-none",
            )}
          >
              <div className="relative flex shrink-0 flex-col items-center pt-2">
                <Drawer.Close asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="absolute right-2 top-1 z-10 h-10 w-10 shrink-0 rounded-full p-0 text-ink hover:bg-input"
                    aria-label="Close query builder"
                  >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                      <path d="M18 6L6 18M6 6l12 12" strokeLinecap="round" />
                    </svg>
                  </Button>
                </Drawer.Close>
                <Drawer.Handle className="mx-auto mb-2 mt-1 h-1.5 w-12 shrink-0 rounded-full bg-border" />
              </div>
              <Drawer.Title className="sr-only">Query builder</Drawer.Title>
              <Drawer.Description className="sr-only">
                Adjust players, metrics, aggregation, and context filters. Results update in the view above.
              </Drawer.Description>
              <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
                <div className="min-h-0 flex-1 overflow-y-auto px-4">
                  <div className="flex flex-col gap-5 pb-2 pt-1">
                    <QueryBuilderSidebarScroll {...sidebarScrollProps} />
                  </div>
                </div>
                <QueryBuilderSidebarExecuteFooter
                  running={running}
                  onExecute={onExecute}
                  className="rounded-none border-t border-border p-3 pt-2"
                />
              </div>
          </Drawer.Content>
        </Drawer.Portal>
      </Drawer.Root>
    </>
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
