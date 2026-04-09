import { useCallback, useMemo, useState } from "react";

import { FormulaSqlEditor } from "@/components/FormulaSqlEditor";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { PLAYER_IDS_TOKEN } from "@/constants/formula";
import { goldUnifiedParquetUrl, playerHubParquetUrl, shardParquetUrl } from "@/lib/api";
import { initDB, mountGoldLayer, mountRemoteShard, runQuery } from "@/lib/duckdb";
import { mergeShardMap } from "@/lib/mergeShards";
import { injectPinnedPlayerIds } from "@/lib/sqlTokens";
import { cn } from "@/lib/utils";
import type { QueryResult } from "@/types/workbench";
import { useWorkbenchStore, type FormulaLabTrack } from "@/store/useWorkbenchStore";

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";

export function FormulaLab() {
  const customFormula = useWorkbenchStore((s) => s.customFormula);
  const setCustomFormula = useWorkbenchStore((s) => s.setCustomFormula);
  const customFormulaTelescope = useWorkbenchStore((s) => s.customFormulaTelescope);
  const setCustomFormulaTelescope = useWorkbenchStore((s) => s.setCustomFormulaTelescope);
  const formulaLabTrack = useWorkbenchStore((s) => s.formulaLabTrack);
  const setFormulaLabTrack = useWorkbenchStore((s) => s.setFormulaLabTrack);
  const pinnedPlayers = useWorkbenchStore((s) => s.pinnedPlayers);
  const playerShardMap = useWorkbenchStore((s) => s.playerShardMap);

  const shards = useMemo(() => mergeShardMap(playerShardMap), [playerShardMap]);

  const activeSql = formulaLabTrack === "telescope" ? customFormulaTelescope : customFormula;
  const setActiveSql = formulaLabTrack === "telescope" ? setCustomFormulaTelescope : setCustomFormula;

  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [goldWarning, setGoldWarning] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const usesPlayerToken = activeSql.includes(PLAYER_IDS_TOKEN);

  const sqlPreview = useMemo(
    () => injectPinnedPlayerIds(activeSql, pinnedPlayers),
    [activeSql, pinnedPlayers],
  );

  const onRun = useCallback(async () => {
    setError(null);
    setGoldWarning(null);
    setResult(null);
    if (usesPlayerToken && pinnedPlayers.length === 0) {
      setError(`Pin at least one player to replace ${PLAYER_IDS_TOKEN}.`);
      return;
    }
    if (formulaLabTrack === "microscope" && shards.length === 0) {
      setError("Pin players so NFL Parquet shards are available for Microscope mode.");
      return;
    }
    setRunning(true);
    try {
      await initDB();

      if (formulaLabTrack === "telescope") {
        try {
          await mountGoldLayer(playerHubParquetUrl(), goldUnifiedParquetUrl());
        } catch {
          setGoldWarning(
            "Could not load player_hub / gold_unified_performance (run the data pipeline and ensure /data serves both files).",
          );
        }
      } else {
        for (const s of shards) {
          const url = shardParquetUrl(s.path);
          await mountRemoteShard(url, `nfl_pbp_${s.year}`);
        }
      }

      const rows = await runQuery(sqlPreview);
      setResult(rows);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }, [
    shards,
    sqlPreview,
    usesPlayerToken,
    pinnedPlayers.length,
    formulaLabTrack,
  ]);

  const statEntries = useMemo(() => {
    if (!result?.rows.length) {
      return [];
    }
    const row = result.rows[0]!;
    return Object.entries(row).map(([k, v]) => ({ label: k, value: formatCell(v) }));
  }, [result]);

  return (
    <Card className="overflow-hidden border-border">
      <Accordion type="single" collapsible className="w-full">
        <AccordionItem value="formula" className="border-0">
          <AccordionTrigger className="px-4 py-4 hover:no-underline md:px-6">
            <div className="flex flex-col items-start gap-1 pr-2 text-left">
              <CardTitle className="text-lg text-ink">Formula Lab</CardTitle>
              <p className="text-xs font-normal text-ink-muted">
                Custom SQL · DuckDB-WASM · {PLAYER_IDS_TOKEN} for pinned GSIS ids
              </p>
            </div>
          </AccordionTrigger>
          <AccordionContent>
            <div className="space-y-4 border-t border-border px-4 pb-6 pt-4 md:px-6">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <span className="text-xs font-medium uppercase tracking-wide text-ink-muted">Data track</span>
                <ToggleGroup
                  type="single"
                  value={formulaLabTrack}
                  onValueChange={(v) => {
                    if (v === "microscope" || v === "telescope") {
                      setFormulaLabTrack(v as FormulaLabTrack);
                    }
                  }}
                  size="sm"
                  className="justify-start"
                >
                  <ToggleGroupItem value="microscope" aria-label="Microscope play-by-play">
                    Microscope (PBP)
                  </ToggleGroupItem>
                  <ToggleGroupItem value="telescope" aria-label="Telescope unified gold">
                    Telescope (career)
                  </ToggleGroupItem>
                </ToggleGroup>
              </div>

              {formulaLabTrack === "microscope" ? (
                <p className="text-sm text-ink-muted">
                  Play-by-play: use{" "}
                  <code className="rounded bg-accent-subtle px-1 font-mono text-xs text-accent">{PLAYER_IDS_TOKEN}</code>{" "}
                  in{" "}
                  <code className="font-mono text-xs text-ink">IN (...)</code> on{" "}
                  <code className="font-mono text-xs text-ink">passer_player_id</code>,{" "}
                  <code className="font-mono text-xs text-ink">rusher_player_id</code>, etc. Loads{" "}
                  <code className="font-mono text-xs text-ink">nfl_pbp_YYYY</code> from pinned shards only.
                </p>
              ) : (
                <p className="text-sm text-ink-muted">
                  Unified gold: filter with{" "}
                  <code className="rounded bg-accent-subtle px-1 font-mono text-xs text-accent">{PLAYER_IDS_TOKEN}</code>{" "}
                  on{" "}
                  <code className="font-mono text-xs text-ink">gold_unified_performance.nfl_id</code> (baked GSIS). Mounts{" "}
                  <code className="font-mono text-xs text-ink">player_hub</code> and{" "}
                  <code className="font-mono text-xs text-ink">gold_unified_performance</code> only (no{" "}
                  <code className="font-mono text-xs text-ink">nfl_pbp_*</code>).
                </p>
              )}

              {goldWarning && (
                <p className="rounded-md border border-warn-fg/25 bg-warn-fg/5 px-3 py-2 text-sm text-warn-fg">
                  {goldWarning}
                </p>
              )}

              <FormulaSqlEditor value={activeSql} onChange={setActiveSql} placeholder="SELECT ..." />

              <div className="flex flex-wrap items-center gap-2">
                <Button type="button" onClick={() => void onRun()} disabled={running}>
                  {running ? "Running…" : "Run"}
                </Button>
                {usesPlayerToken && pinnedPlayers.length === 0 && (
                  <span className="text-xs text-warn-fg">Pin players to fill {PLAYER_IDS_TOKEN}.</span>
                )}
                {usesPlayerToken && pinnedPlayers.length > 0 && (
                  <span className="text-xs text-ink-muted">
                    {pinnedPlayers.length} id{pinnedPlayers.length === 1 ? "" : "s"} injected at run.
                  </span>
                )}
              </div>

              {error && (
                <p className="rounded-md border border-danger/25 bg-danger/5 px-3 py-2 text-sm text-danger-fg">{error}</p>
              )}

              {result && (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {statEntries.map(({ label, value }) => (
                    <div
                      key={label}
                      className={cn(
                        "rounded-md border border-border bg-input/50 px-4 py-3",
                        "shadow-inner",
                      )}
                    >
                      <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">{label}</p>
                      <p className="mt-1 font-mono text-lg text-accent">{value}</p>
                    </div>
                  ))}
                </div>
              )}

              {result && result.rows.length > 1 && (
                <p className="text-xs text-ink-muted">
                  Showing metrics from the first row ({result.rows.length} rows returned).
                </p>
              )}
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </Card>
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
