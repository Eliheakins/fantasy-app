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

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

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
    <Card className="border-emerald-900/50 bg-zinc-950/90">
      <CardHeader>
        <CardTitle className="text-emerald-400">Formula Lab</CardTitle>
        <p className="text-sm text-zinc-500">
          SQL runs in DuckDB-WASM in your browser. Use{" "}
          <code className="rounded bg-violet-500/20 px-1 text-violet-300">{PLAYER_IDS_TOKEN}</code> where quoted
          GSIS ids should go (for example inside <code className="text-zinc-400">IN (...)</code>). Mounts views{" "}
          <code className="text-zinc-300">nfl_pbp_YYYY</code> from pinned players&apos; shards.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
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
            <span className="text-xs text-amber-500">Pin players to fill {PLAYER_IDS_TOKEN}.</span>
          )}
          {usesPlayerToken && pinnedPlayers.length > 0 && (
            <span className="text-xs text-zinc-500">
              {pinnedPlayers.length} id{pinnedPlayers.length === 1 ? "" : "s"} injected at run.
            </span>
          )}
        </div>

        {error && (
          <p className="rounded border border-red-900/60 bg-red-950/40 px-3 py-2 text-sm text-red-200">
            {error}
          </p>
        )}

        {result && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {statEntries.map(({ label, value }) => (
              <div
                key={label}
                className={cn(
                  "rounded-md border border-zinc-800 bg-zinc-900/60 px-4 py-3",
                  "shadow-inner",
                )}
              >
                <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</p>
                <p className="mt-1 font-mono text-lg text-zinc-100">{value}</p>
              </div>
            ))}
          </div>
        )}

        {result && result.rows.length > 1 && (
          <p className="text-xs text-zinc-500">
            Showing metrics from the first row ({result.rows.length} rows returned).
          </p>
        )}
      </CardContent>
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
