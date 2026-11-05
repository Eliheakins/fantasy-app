import { MAX_PINNED_PLAYERS } from "@/stat/lib/queryUrl";
import { usePinnedPlayers } from "@/features/explore/usePinnedPlayers";
import { useQueryState } from "@/features/explore/useQueryState";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Pinned players as removable chips (used under The Who).
 */
export function PinnedPlayersBar() {
  const { state, unpinPlayer, clearPins } = useQueryState();
  const pinnedPlayers = usePinnedPlayers(state.players);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-caption text-muted">Pinned · max {MAX_PINNED_PLAYERS}</p>
        {pinnedPlayers.length > 0 && (
          <Button type="button" variant="ghost" className="shrink-0 text-caption" onClick={() => clearPins()}>
            Clear all
          </Button>
        )}
      </div>

      {pinnedPlayers.length === 0 ? (
        <p className="rounded-lg border border-dashed border-line bg-surface py-6 text-center text-body text-muted">
          Pin players from search to compare.
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {pinnedPlayers.map((p) => (
            <div
              key={p.gsis_id}
              className={cn(
                "inline-flex max-w-full items-center gap-1 rounded-full border border-line bg-surface py-1 pl-3 pr-1 shadow-xs",
                              )}
            >
              <span className="min-w-0 truncate text-body font-medium text-ink">{p.full_name ?? p.gsis_id}</span>
              <span className="hidden text-caption text-muted sm:inline">
                {p.team ?? "—"} · {p.position ?? "—"}
              </span>
              <button
                type="button"
                onClick={() => unpinPlayer(p.gsis_id)}
                className="flex h-11 w-11 shrink-0 md:h-7 md:w-7 items-center justify-center rounded-full text-muted transition hover:bg-warning-bg hover:text-warning"
                aria-label={`Unpin ${p.full_name ?? p.gsis_id}`}
              >
                <span className="text-heading leading-none">×</span>
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
