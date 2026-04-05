import { MAX_PINNED_PLAYERS, useWorkbenchStore } from "@/store/useWorkbenchStore";

import { Button } from "@/components/ui/button";

/**
 * The Who — horizontal strip of pinned player cards.
 */
export function PinnedPlayersBar() {
  const pinnedPlayers = useWorkbenchStore((s) => s.pinnedPlayers);
  const unpinPlayer = useWorkbenchStore((s) => s.unpinPlayer);
  const clearPins = useWorkbenchStore((s) => s.clearPins);

  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-950/80 p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-400">The Who</h2>
          <p className="text-xs text-zinc-600">Pinned players · max {MAX_PINNED_PLAYERS}</p>
        </div>
        {pinnedPlayers.length > 0 && (
          <Button type="button" variant="ghost" className="h-8 shrink-0 text-xs" onClick={() => clearPins()}>
            Clear all
          </Button>
        )}
      </div>

      {pinnedPlayers.length === 0 ? (
        <p className="rounded-lg border border-dashed border-zinc-800 bg-zinc-900/30 py-8 text-center text-sm text-zinc-500">
          Pin players from search to see them here.
        </p>
      ) : (
        <div className="flex gap-3 overflow-x-auto pb-1 pt-0.5 [scrollbar-gutter:stable]">
          {pinnedPlayers.map((p) => (
            <article
              key={p.gsis_id}
              className="flex min-w-[200px] max-w-[240px] shrink-0 flex-col rounded-lg border border-zinc-700 bg-zinc-900/60 p-3 shadow-sm"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-medium text-zinc-100">{p.full_name ?? p.gsis_id}</p>
                  <p className="truncate text-xs text-zinc-500">
                    {p.team ?? "—"} · {p.position ?? "—"}
                  </p>
                  <p className="mt-1 font-mono text-[10px] text-zinc-500">{p.gsis_id}</p>
                </div>
                <button
                  type="button"
                  onClick={() => unpinPlayer(p.gsis_id)}
                  className="shrink-0 rounded-md p-1 text-zinc-500 transition hover:bg-zinc-800 hover:text-zinc-200"
                  aria-label={`Unpin ${p.full_name ?? p.gsis_id}`}
                >
                  <span className="block text-base leading-none">×</span>
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
