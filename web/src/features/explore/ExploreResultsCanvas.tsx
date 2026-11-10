import { PlayerLink } from "@/components/PlayerLink";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { buildScatterPoints, StatScatterChart } from "@/features/explore/StatScatterChart";
import { Callout } from "@/components/Callout";
import { CollapsibleCode } from "@/components/CollapsibleCode";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { getStatById } from "@/stat/config/statDictionary";
import { TEAMS } from "@/stat/config/teams";
import { formatMetricValueHeader, metricSelectAlias } from "@/stat/lib/queryBuilder";
import { formatQueryValue } from "@/stat/lib/formatQueryValue";
import type { NFLPlayer, QueryResult } from "@/stat/types/workbench";
import { useQueryState } from "@/stat/react/useQueryState";
import { useLeagueName } from "@/lib/league";
import { useLeagueOwners } from "@/features/explore/useLeagueOwners";
import { isLeagueQuery } from "@/stat/lib/queryUrl";
import { compareHref, MAX_COMPARE, withoutPlayer } from "@/features/players/profile";

export interface ExploreResultsCanvasProps {
  result: QueryResult | null;
  error: string | null;
  details: string | null;
  running: boolean;
  pinnedPlayers: NFLPlayer[];
  /** Everyone the rows name; for a leaderboard these are the ranked players. Defaults to the pinned players. */
  namedPlayers?: NFLPlayer[];
}

export function ExploreResultsCanvas({ result, error, details, running, pinnedPlayers, namedPlayers }: ExploreResultsCanvasProps) {
  const { state } = useQueryState();
  const selectedStatIds = state.stats;
  const activeGranularity = state.granularity;

  const leagueName = useLeagueName();
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
      ["posteam_type", "Home or away"],
    ]);
    for (const id of selectedStatIds) {
      const st = getStatById(id);
      headers.set(metricSelectAlias(id), formatMetricValueHeader(st, activeGranularity, leagueName));
    }
    return headers;
  }, [selectedStatIds, activeGranularity, leagueName]);

  const forTeams = state.subject === "teams";
  const { byPlayer: owners } = useLeagueOwners();
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
  const positionByGsis = useMemo(
    () => new Map((namedPlayers ?? pinnedPlayers).map((p) => [p.gsis_id, p.position ?? ""])),
    [pinnedPlayers, namedPlayers],
  );
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
    return buildScatterPoints(result.rows as Record<string, unknown>[], xCol, yCol, nameByGsis, idColumn);
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

  const { search } = useLocation();
  const [compared, setCompared] = useState<string[]>([]);
  const toggleCompared = (id: string) =>
    setCompared((ids) => (ids.includes(id) ? withoutPlayer(ids, id) : ids.length >= MAX_COMPARE ? ids : [...ids, id]));
  const teamByGsis = useMemo(
    () => new Map((namedPlayers ?? pinnedPlayers).map((p) => [p.gsis_id, p.team ?? ""])),
    [pinnedPlayers, namedPlayers],
  );
  const rowCount = result?.rows.length ?? 0;

  return (
    <section aria-labelledby="explore-results-heading" className="min-h-[160px] space-y-3 overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 id="explore-results-heading" className="text-section font-semibold">
            {rowCount > 0
              ? `${rowCount} ${forTeams ? (rowCount === 1 ? "team" : "teams") : rowCount === 1 ? "player" : "players"}`
              : "Results"}
          </h2>
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
              <Button type="button" variant="outline" size="sm" onClick={() => setSwapScatterAxes((s) => !s)}>
                Swap axes
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
      <div className="space-y-3 text-body">
        {running && <p className="text-caption text-muted">Updating…</p>}
        {error ? <Callout variant="error">{error}</Callout> : null}
        {(result?.notices ?? []).map((notice) => (
          <Callout key={notice} variant="warn">
            {notice}
          </Callout>
        ))}

        {result && result.rows.length > 0 ? (
          canvasView === "scatter" && twoStatsMode ? (
            <div className="flex justify-center overflow-x-auto rounded-md border border-line bg-surface py-4">
              <StatScatterChart points={scatterPoints} xLabel={scatterXLabel} yLabel={scatterYLabel} />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-body">
                <thead>
                  <tr className="border-b-[1.5px] border-forest">
                    {!forTeams && (
                      <th className="w-11 px-3 py-2 font-medium text-muted">
                        <span className="sr-only">Compare</span>
                      </th>
                    )}
                    <th className="px-3 py-2 font-medium text-muted">{forTeams ? "Team" : "Player"}</th>
                    {!forTeams && <th className="px-3 py-2 font-medium text-muted">Team</th>}
                    {!forTeams && <th className="px-3 py-2 font-medium text-muted">Pos</th>}
                    {result.columns
                      .filter((col) => col !== idColumn)
                      .map((col) => (
                        <th key={col} className="px-3 py-2 text-right font-medium text-muted">
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
                      <tr key={`${pid}-${i}`} className="border-b border-line last:border-0">
                        {!forTeams && (
                          <td className="px-3 py-1">
                            <input
                              type="checkbox"
                              checked={compared.includes(pid)}
                              disabled={!compared.includes(pid) && compared.length >= MAX_COMPARE}
                              onChange={() => toggleCompared(pid)}
                              aria-label={`Compare ${label}`}
                              className="h-5 w-5 accent-focus"
                            />
                          </td>
                        )}
                        <td className="px-3 py-2 font-medium text-ink">
                          {forTeams ? label : <PlayerLink gsisId={pid || null} name={label} position={positionByGsis.get(pid) ?? ""} />}
                          {/* The owner on every row is intended (issue #70); a free agent is marked once a league is chosen. */}
                          {!forTeams && owners?.get(pid) ? (
                            <span className="ml-2 text-caption font-normal text-muted">
                              <span className="sr-only">, owned by </span>
                              {owners.get(pid)!.owner}
                            </span>
                          ) : null}
                          {!forTeams && owners && !owners.get(pid) ? (
                            <span className="ml-2 rounded-full bg-panel px-2 py-0.5 text-caption font-semibold text-forest">
                              Free agent
                            </span>
                          ) : null}
                        </td>
                        {!forTeams && <td className="px-3 py-2 text-ink">{teamByGsis.get(pid) || "—"}</td>}
                        {!forTeams && <td className="px-3 py-2 text-ink">{positionByGsis.get(pid) || "—"}</td>}
                        {result.columns
                          .filter((col) => col !== idColumn)
                          .map((col) => (
                            <td key={col} className="px-3 py-2 text-right tabular-nums text-ink">
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
          <p className="text-muted">Query returned no rows for this combination of filters.</p>
        ) : !error && !running && !hasSubject ? (
          <p className="text-muted">
            {forTeams
              ? "Pick teams from the Teams chip, or set a ranking with none picked to rank all 32."
              : "Add players from the Players chip, or rank everyone by a stat with the ranking chip."}
          </p>
        ) : !error && !running && hasSubject && selectedStatIds.length === 0 ? (
          <p className="text-muted">Add a stat with “+ stat” to load the results.</p>
        ) : null}

        {compared.length > 0 ? (
          <div
            role="region"
            aria-label="Compare selection"
            className="sticky bottom-0 -mx-1 flex flex-wrap items-center gap-3 rounded-xl bg-forest px-4 py-3 text-white"
          >
            <p className="min-w-0 flex-1 text-body">
              {compared.length} selected{compared.length < 2 ? ". Pick one more to compare." : ""}
            </p>
            {compared.length >= 2 ? (
              <Link
                to={compareHref(compared, search)}
                className="inline-flex min-h-11 items-center rounded-full bg-chrome-accent px-5 text-body font-bold text-forest"
              >
                Compare
              </Link>
            ) : null}
            <button type="button" onClick={() => setCompared([])} className="min-h-11 px-3 text-body underline">
              Clear
            </button>
          </div>
        ) : null}

        {details ? <CollapsibleCode title="Query details" code={details} /> : null}
      </div>
    </section>
  );
}
