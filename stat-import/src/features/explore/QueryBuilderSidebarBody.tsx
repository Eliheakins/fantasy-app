import { DATA_BASE_URL } from "@/shared/lib/config";
import { cn } from "@/shared/lib/utils";
import type { NFLPlayer } from "@/shared/types/workbench";
import { MAX_PINNED_PLAYERS } from "@/shared/lib/queryUrl";

import { AggregationSection } from "@/features/explore/AggregationSection";
import { FilterChipsBar } from "@/features/explore/FilterChipsBar";
import { PinnedPlayersBar } from "@/features/explore/PinnedPlayersBar";
import { StatDictionaryPanel } from "@/features/explore/StatDictionaryPanel";
import { TeamPicker } from "@/features/explore/TeamPicker";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/shared/components/ui/toggle-group";
import { useQueryState } from "@/shared/lib/useQueryState";

export interface QueryBuilderSidebarScrollProps {
  query: string;
  setQuery: (v: string) => void;
  debounced: string;
  suggestions: NFLPlayer[];
  isPinned: (gsisId: string) => boolean;
  pinnedPlayers: NFLPlayer[];
  onSelectPlayer: (p: NFLPlayer) => void;
  pinMessage: string | null;
  searchError: string | null;
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
  searchError,
}: QueryBuilderSidebarScrollProps) {
  const { state, setSubject } = useQueryState();
  const forTeams = state.subject === "teams";

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
        <ToggleGroup
          type="single"
          value={state.subject}
          onValueChange={(subject) => {
            if (subject === "players" || subject === "teams") {
              setSubject(subject);
            }
          }}
          className="flex gap-2"
          aria-label="Players or teams"
        >
          <ToggleGroupItem value="players" className="rounded-md">
            Players
          </ToggleGroupItem>
          <ToggleGroupItem value="teams" className="rounded-md">
            Teams
          </ToggleGroupItem>
        </ToggleGroup>
        {forTeams ? (
          <TeamPicker />
        ) : (
          <>
            <div className="relative">
              <Input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search players…"
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
            {searchError && <p className="text-sm text-danger-fg">{searchError}</p>}
            {pinMessage && <p className="text-sm text-warn-fg">{pinMessage}</p>}
            <p className="text-[10px] text-ink-muted">
              Data: {DATA_BASE_URL} · Pin up to {MAX_PINNED_PLAYERS} players to compare
            </p>
            <PinnedPlayersBar />
          </>
        )}
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
      <Button
        type="button"
        className="h-11 w-full min-h-[44px] text-sm font-semibold shadow-sm"
        onClick={onExecute}
        disabled={running}
      >
        {running ? "Running…" : "Execute analysis"}
      </Button>
    </div>
  );
}
