import { useEffect, useMemo, useState } from "react";

import {
  buildScatterPoints,
  StatScatterChart,
} from "@/features/explore/StatScatterChart";
import { Callout } from "@/shared/components/Callout";
import { CollapsibleCode } from "@/shared/components/CollapsibleCode";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { ToggleGroup, ToggleGroupItem } from "@/shared/components/ui/toggle-group";
import { getStatById } from "@/shared/config/statDictionary";
import { TEAMS } from "@/shared/config/teams";
import {
  formatMetricValueHeader,
  metricSelectAlias,
} from "@/shared/lib/queryBuilder";
import { formatQueryValue } from "@/shared/lib/formatQueryValue";
import type { NFLPlayer, QueryResult } from "@/shared/types/workbench";
import { useQueryState } from "@/shared/lib/useQueryState";
import { isLeagueQuery } from "@/shared/lib/queryUrl";

export interface ExploreResultsCanvasProps {
  result: QueryResult | null;
  error: string | null;
  details: string | null;
  running: boolean;
  pinnedPlayers: NFLPlayer[];
  /** Everyone the rows name; for a leaderboard these are the ranked players. Defaults to the pinned players. */
  namedPlayers?: NFLPlayer[];
}

export function ExploreResultsCanvas({
  result,
  error,
  details,
  running,
  pinnedPlayers,
  namedPlayers,
}: ExploreResultsCanvasProps) {
  const { state } = useQueryState();
  const selectedStatIds = state.stats;
  const activeGranularity = state.granularity;
  const minPlays = state.minPlays;

  const [canvasView, setCanvasView] = useState<"table" | "scatter">("table");
  const [swapScatterAxes, setSwapScatterAxes] = useState(false);

  // The chart plots one dot per player, which a season or week split would repeat.
  const twoStatsMode = selectedStatIds.length === 2 && state.split === null;

  useEffect(() => {
    if (!twoStatsMode) {
      setCanvasView("table");
      setSwapScatterAxes(false);
    }
  }, [twoStatsMode]);

  const columnHeaders = useMemo(() => {
    const headers = new Map<string, string>([
      ["season", "Season"],
      ["week", "Week"],
    ]);
    for (const id of selectedStatIds) {
      const st = getStatById(id);
      headers.set(metricSelectAlias(id), formatMetricValueHeader(st, activeGranularity));
    }
    return headers;
  }, [selectedStatIds, activeGranularity]);

  const forTeams = state.subject === "teams";
  const idColumn = forTeams ? "team_id" : "player_id";

  // Who each row is: a player's name, or a team's.
  const nameByGsis = useMemo(() => {
    if (forTeams) {
      return new Map(TEAMS.map((t) => [t.id, t.name]));
    }
    const m = new Map<string, string>();
    for (const p of namedPlayers ?? pinnedPlayers) {
      m.set(p.gsis_id, p.full_name ?? p.gsis_id);
    }
    return m;
  }, [forTeams, pinnedPlayers, namedPlayers]);
  const hasSubject = isLeagueQuery(state) || (forTeams ? state.teams.length > 0 : pinnedPlayers.length > 0);

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
      idColumn,
    );
  }, [result, twoStatsMode, selectedStatIds, swapScatterAxes, nameByGsis, idColumn]);

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
    const ranking =
      state.order && state.limit !== null
        ? ` · ${state.order.direction === "desc" ? "top" : "bottom"} ${state.limit} by ${getStatById(state.order.metric)?.label ?? state.order.metric}`
        : "";
    const split = state.split ? ` · by ${state.split}` : "";
    return `${labels.join(" · ")} · ${gran} · min ${minPlays} plays${ranking}${split}`;
  }, [selectedStatIds, activeGranularity, minPlays, state.order, state.limit, state.split]);

  return (
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
        {error ? <Callout variant="danger">{error}</Callout> : null}

        {result && result.rows.length > 0 ? (
          canvasView === "scatter" && twoStatsMode ? (
            <div className="flex justify-center overflow-x-auto rounded-md border border-border bg-input/40 py-4">
              <StatScatterChart points={scatterPoints} xLabel={scatterXLabel} yLabel={scatterYLabel} />
            </div>
          ) : (
            <div className="overflow-x-auto rounded-md border border-border">
              <table className="w-full border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b border-border bg-input/60">
                    <th className="px-3 py-2 font-medium text-ink-muted">{forTeams ? "Team" : "Player"}</th>
                    {result.columns
                      .filter((col) => col !== idColumn)
                      .map((col) => (
                        <th key={col} className="px-3 py-2 font-medium text-ink-muted">
                          {columnHeaders.get(col) ?? col}
                        </th>
                      ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((row, i) => {
                    const pid = String(row[idColumn] ?? "");
                    const label = nameByGsis.get(pid) ?? pid;
                    return (
                      <tr key={`${pid}-${i}`} className="border-b border-border/80 last:border-0">
                        <td className="px-3 py-2 font-medium text-ink">{label}</td>
                        {result.columns
                          .filter((col) => col !== idColumn)
                          .map((col) => (
                            <td key={col} className="px-3 py-2 font-mono text-accent">
                              {formatQueryValue(row[col])}
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
        ) : !error && !running && !hasSubject ? (
          <p className="text-ink-muted">
            {forTeams ? (
              <span>Pick teams in The Who, or set a ranking with none picked to rank all 32. </span>
            ) : (
              <>
                <span className="lg:hidden">Open the query builder (bottom-right) to search and pin players. </span>
                <span className="hidden lg:inline">Pin players to load data. </span>
              </>
            )}
            Stats, granularity, min plays, and filter changes refresh the table automatically.
          </p>
        ) : !error && !running && hasSubject && selectedStatIds.length === 0 ? (
          <p className="text-ink-muted">
            <span className="lg:hidden">Open the query builder and pick metrics under The What. </span>
            <span className="hidden lg:inline">Select at least one metric in The What to load the canvas.</span>
          </p>
        ) : null}

        {details ? <CollapsibleCode title="Query details" code={details} /> : null}
      </CardContent>
    </Card>
  );
}
