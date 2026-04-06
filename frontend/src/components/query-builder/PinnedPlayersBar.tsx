import { MAX_PINNED_PLAYERS, useWorkbenchStore } from "@/store/useWorkbenchStore";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Pinned players as removable chips (used under The Who).
 */
export function PinnedPlayersBar() {
  const pinnedPlayers = useWorkbenchStore((s) => s.pinnedPlayers);
  const unpinPlayer = useWorkbenchStore((s) => s.unpinPlayer);
  const clearPins = useWorkbenchStore((s) => s.clearPins);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-ink-muted">Pinned · max {MAX_PINNED_PLAYERS}</p>
        {pinnedPlayers.length > 0 && (
          <Button type="button" variant="ghost" className="h-8 shrink-0 text-xs" onClick={() => clearPins()}>
            Clear all
          </Button>
        )}
      </div>

      {pinnedPlayers.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border bg-input/50 py-6 text-center text-sm text-ink-muted">
          Pin players from search to compare.
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {pinnedPlayers.map((p) => (
            <div
              key={p.gsis_id}
              className={cn(
                "inline-flex max-w-full items-center gap-1 rounded-full border border-border bg-surface py-1 pl-3 pr-1 shadow-sm",
                "ring-1 ring-black/[0.03]",
              )}
            >
              <span className="min-w-0 truncate text-sm font-medium text-ink">{p.full_name ?? p.gsis_id}</span>
              <span className="hidden text-xs text-ink-muted sm:inline">
                {p.team ?? "—"} · {p.position ?? "—"}
              </span>
              <button
                type="button"
                onClick={() => unpinPlayer(p.gsis_id)}
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-ink-muted transition hover:bg-danger/10 hover:text-danger-fg"
                aria-label={`Unpin ${p.full_name ?? p.gsis_id}`}
              >
                <span className="text-lg leading-none">×</span>
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
