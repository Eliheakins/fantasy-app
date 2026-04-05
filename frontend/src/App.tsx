import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";

import { FormulaLab } from "@/components/FormulaLab";
import { QueryBuilderPanel } from "@/components/query-builder/QueryBuilderPanel";
import { initDB } from "@/lib/duckdb";
import { API_BASE, fetchPlayerDetail, searchPlayers } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { NFLPlayer } from "@/types/workbench";
import { MAX_PINNED_PLAYERS, useWorkbenchStore } from "@/store/useWorkbenchStore";

export default function App() {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [pinMessage, setPinMessage] = useState<string | null>(null);

  const isEngineReady = useWorkbenchStore((s) => s.isEngineReady);
  const setEngineReady = useWorkbenchStore((s) => s.setEngineReady);
  const pinnedPlayers = useWorkbenchStore((s) => s.pinnedPlayers);
  const tryPinPlayer = useWorkbenchStore((s) => s.tryPinPlayer);

  const [engineError, setEngineError] = useState<string | null>(null);

  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(query), 250);
    return () => window.clearTimeout(t);
  }, [query]);

  const searchQ = useQuery({
    queryKey: ["search", debounced],
    queryFn: () => searchPlayers(debounced),
    enabled: debounced.trim().length >= 2,
  });

  useEffect(() => {
    let cancelled = false;
    void initDB()
      .then(() => {
        if (!cancelled) {
          setEngineError(null);
          setEngineReady(true);
        }
      })
      .catch((e) => {
        console.error(e);
        if (!cancelled) {
          setEngineReady(false);
          setEngineError(e instanceof Error ? e.message : String(e));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [setEngineReady]);

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

  return (
    <div className="relative min-h-screen bg-zinc-950 text-zinc-100">
      {!isEngineReady && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-zinc-950/90 backdrop-blur-sm">
          {engineError ? (
            <p className="max-w-md text-center text-sm text-red-300">
              DuckDB failed to start: {engineError}
            </p>
          ) : (
            <>
              <div className="h-10 w-10 animate-spin rounded-full border-2 border-emerald-500 border-t-transparent" />
              <p className="text-sm text-zinc-400">Starting DuckDB-WASM…</p>
            </>
          )}
        </div>
      )}

      <header className="border-b border-zinc-800 bg-zinc-950/80 px-4 py-6">
        <div className="mx-auto flex max-w-5xl flex-col gap-2">
          <h1 className="text-2xl font-semibold tracking-tight text-emerald-400">The Bridge</h1>
          <p className="text-sm text-zinc-500">Football data workbench · Parquet in the browser</p>
          <div className="relative mt-2 max-w-xl">
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search players…"
              className={cn(
                "w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm",
                "placeholder:text-zinc-600 focus:outline-none focus:ring-2 focus:ring-emerald-600",
              )}
            />
            {suggestions.length > 0 && debounced.trim().length >= 2 && (
              <ul
                className="absolute z-10 mt-1 max-h-64 w-full overflow-auto rounded-md border border-zinc-700 bg-zinc-900 py-1 shadow-lg"
                role="listbox"
              >
                {suggestions.map((p) => (
                  <li key={p.gsis_id}>
                    <button
                      type="button"
                      disabled={isPinned(p.gsis_id) || pinnedPlayers.length >= MAX_PINNED_PLAYERS}
                      className={cn(
                        "flex w-full flex-col items-start px-3 py-2 text-left text-sm hover:bg-zinc-800",
                        (isPinned(p.gsis_id) || pinnedPlayers.length >= MAX_PINNED_PLAYERS) &&
                          "cursor-not-allowed opacity-50 hover:bg-transparent",
                      )}
                      onClick={() => void onSelectPlayer(p)}
                    >
                      <span className="font-medium text-zinc-100">{p.full_name ?? p.gsis_id}</span>
                      <span className="text-xs text-zinc-500">
                        {p.team ?? "—"} · {p.position ?? "—"}
                        {isPinned(p.gsis_id) ? " · pinned" : ""}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {pinMessage && <p className="text-sm text-amber-500">{pinMessage}</p>}
          <p className="text-xs text-zinc-600">
            API: {API_BASE} · Pin up to {MAX_PINNED_PLAYERS} players for formulas
          </p>
        </div>
      </header>

      <main className="space-y-8 px-4 py-8">
        <section className="mx-auto max-w-7xl space-y-2">
          <h2 className="text-lg font-medium text-zinc-200">Query builder</h2>
          <p className="text-sm text-zinc-500">
            Pick who to compare, up to five metrics, and context filters — separate from the Formula Lab below.
          </p>
          <QueryBuilderPanel />
        </section>

        <section className="mx-auto max-w-5xl space-y-2">
          <h2 className="text-lg font-medium text-zinc-200">Formula Lab</h2>
          <p className="text-sm text-zinc-500">
            Raw SQL with <code className="text-zinc-400">{"{{PLAYER_IDS}}"}</code> and mounted Parquet shards.
          </p>
          <FormulaLab />
        </section>
      </main>
    </div>
  );
}
