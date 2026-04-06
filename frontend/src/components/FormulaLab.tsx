import { useCallback, useMemo, useState } from "react";

import { FormulaSqlEditor } from "@/components/FormulaSqlEditor";
import { PLAYER_IDS_TOKEN } from "@/constants/formula";
import { initDB, mountRemoteShard, runQuery } from "@/lib/duckdb";
import { shardParquetUrl } from "@/lib/api";
import { mergeShardMap } from "@/lib/mergeShards";
import { injectPinnedPlayerIds } from "@/lib/sqlTokens";
import { cn } from "@/lib/utils";
import type { QueryResult } from "@/types/workbench";
import { useWorkbenchStore } from "@/store/useWorkbenchStore";

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";

export function FormulaLab() {
  const customFormula = useWorkbenchStore((s) => s.customFormula);
  const setCustomFormula = useWorkbenchStore((s) => s.setCustomFormula);
  const pinnedPlayers = useWorkbenchStore((s) => s.pinnedPlayers);
  const playerShardMap = useWorkbenchStore((s) => s.playerShardMap);

  const shards = useMemo(() => mergeShardMap(playerShardMap), [playerShardMap]);

  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const usesPlayerToken = customFormula.includes(PLAYER_IDS_TOKEN);

  const sqlPreview = useMemo(
    () => injectPinnedPlayerIds(customFormula, pinnedPlayers),
    [customFormula, pinnedPlayers],
  );

  const onRun = useCallback(async () => {
    setError(null);
    setResult(null);
    if (usesPlayerToken && pinnedPlayers.length === 0) {
      setError(`Pin at least one player to replace ${PLAYER_IDS_TOKEN}.`);
      return;
    }
    setRunning(true);
    try {
      await initDB();

      for (const s of shards) {
        const url = shardParquetUrl(s.path);
        await mountRemoteShard(url, `nfl_pbp_${s.year}`);
      }

      const rows = await runQuery(sqlPreview);
      setResult(rows);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }, [shards, sqlPreview, usesPlayerToken, pinnedPlayers.length]);

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
                Custom SQL · DuckDB-WASM · {PLAYER_IDS_TOKEN} for pinned ids
              </p>
            </div>
          </AccordionTrigger>
          <AccordionContent>
            <div className="space-y-4 border-t border-border px-4 pb-6 pt-4 md:px-6">
              <p className="text-sm text-ink-muted">
                Raw SQL with DuckDB-WASM in your browser. Use{" "}
                <code className="rounded bg-accent-subtle px-1 font-mono text-xs text-accent">{PLAYER_IDS_TOKEN}</code>{" "}
                where quoted GSIS ids should go (for example inside{" "}
                <code className="font-mono text-xs text-ink">IN (...)</code>). Mounts views{" "}
                <code className="font-mono text-xs text-ink">nfl_pbp_YYYY</code> from pinned players&apos; shards.
              </p>

              <FormulaSqlEditor
                value={customFormula}
                onChange={setCustomFormula}
                placeholder="SELECT ..."
              />

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
