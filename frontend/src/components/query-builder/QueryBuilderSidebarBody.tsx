import { API_BASE } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { NFLPlayer } from "@/types/workbench";
import { MAX_PINNED_PLAYERS } from "@/store/useWorkbenchStore";

import { AggregationSection } from "@/components/query-builder/AggregationSection";
import { FilterChipsBar } from "@/components/query-builder/FilterChipsBar";
import { PinnedPlayersBar } from "@/components/query-builder/PinnedPlayersBar";
import { StatDictionaryPanel } from "@/components/query-builder/StatDictionaryPanel";
import { Button } from "@/components/ui/button";

export interface QueryBuilderSidebarScrollProps {
  query: string;
  setQuery: (v: string) => void;
  debounced: string;
  suggestions: NFLPlayer[];
  isPinned: (gsisId: string) => boolean;
  pinnedPlayers: NFLPlayer[];
  onSelectPlayer: (p: NFLPlayer) => void;
  pinMessage: string | null;
}

/**
 * Shared scrollable query-builder column (desktop sidebar or mobile sheet).
 */
export function QueryBuilderSidebarScroll({
  query,
  setQuery,
  debounced,
  suggestions,
  isPinned,
  pinnedPlayers,
  onSelectPlayer,
  pinMessage,
}: QueryBuilderSidebarScrollProps) {
  return (
    <>
      <div>
        <h1 className="text-lg font-bold tracking-tight text-ink">Query Builder</h1>
        <p className="mt-0.5 text-[10px] font-semibold uppercase tracking-widest text-accent-muted">
          Precision filter engine
        </p>
      </div>

      <section className="space-y-3 border-b border-border pb-5">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-muted">The Who</h2>
        <div className="relative">
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search players…"
            className={cn(
              "min-h-[44px] w-full rounded-md border border-border bg-input px-3 py-2 text-base text-ink sm:text-sm",
              "placeholder:text-ink-muted focus:outline-none focus:ring-2 focus:ring-primary",
            )}
          />
          {suggestions.length > 0 && debounced.trim().length >= 2 && (
            <ul
              className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-md border border-border bg-surface py-1 shadow-card"
              role="listbox"
            >
              {suggestions.map((p) => (
                <li key={p.gsis_id}>
                  <button
                    type="button"
                    disabled={isPinned(p.gsis_id) || pinnedPlayers.length >= MAX_PINNED_PLAYERS}
                    className={cn(
                      "flex min-h-[44px] w-full flex-col items-start justify-center px-3 py-2 text-left text-sm hover:bg-input",
                      (isPinned(p.gsis_id) || pinnedPlayers.length >= MAX_PINNED_PLAYERS) &&
                        "cursor-not-allowed opacity-50 hover:bg-transparent",
                    )}
                    onClick={() => void onSelectPlayer(p)}
                  >
                    <span className="font-medium text-ink">{p.full_name ?? p.gsis_id}</span>
                    <span className="text-xs text-ink-muted">
                      {p.team ?? "—"} · {p.position ?? "—"}
                      {isPinned(p.gsis_id) ? " · pinned" : ""}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        {pinMessage && <p className="text-sm text-warn-fg">{pinMessage}</p>}
        <p className="text-[10px] text-ink-muted">
          API: {API_BASE} · Pin up to {MAX_PINNED_PLAYERS} players for formulas
        </p>
        <PinnedPlayersBar />
      </section>

      <StatDictionaryPanel />

      <AggregationSection />

      <FilterChipsBar />
    </>
  );
}

export function QueryBuilderSidebarExecuteFooter({
  running,
  onExecute,
  className,
}: {
  running: boolean;
  onExecute: () => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "shrink-0 border-t border-border bg-surface p-4 pb-[max(1rem,env(safe-area-inset-bottom))]",
        className,
      )}
    >
      <Button type="button" className="h-11 w-full min-h-[44px] text-sm font-semibold shadow-sm" onClick={onExecute} disabled={running}>
        {running ? "Running…" : "Execute analysis"}
      </Button>
    </div>
  );
}
