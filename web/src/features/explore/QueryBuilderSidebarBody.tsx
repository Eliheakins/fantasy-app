import { cn } from "@/lib/utils";
import type { NFLPlayer } from "@/stat/types/workbench";
import { MAX_PINNED_PLAYERS } from "@/stat/lib/queryUrl";

import { AggregationSection } from "@/features/explore/AggregationSection";
import { FilterChipsBar } from "@/features/explore/FilterChipsBar";
import { LeagueFilterControl } from "@/features/explore/LeagueFilterControl";
import { PinnedPlayersBar } from "@/features/explore/PinnedPlayersBar";
import { StatDictionaryPanel } from "@/features/explore/StatDictionaryPanel";
import { TeamPicker } from "@/features/explore/TeamPicker";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useQueryState } from "@/features/explore/useQueryState";

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
      <section className="space-y-3 border-b border-line pb-5">
        <h2 className="text-body font-semibold uppercase tracking-wide text-muted">The Who</h2>
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
                  className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-md border border-line bg-panel py-1 shadow-sm"
                  role="listbox"
                >
                  {suggestions.map((p) => (
                    <li key={p.gsis_id}>
                      <button
                        type="button"
                        disabled={isPinned(p.gsis_id) || pinnedPlayers.length >= MAX_PINNED_PLAYERS}
                        className={cn(
                          "flex min-h-[44px] w-full flex-col items-start justify-center px-3 py-2 text-left text-body hover:bg-panel",
                          (isPinned(p.gsis_id) || pinnedPlayers.length >= MAX_PINNED_PLAYERS) &&
                            "cursor-not-allowed opacity-50 hover:bg-transparent",
                        )}
                        onClick={() => void onSelectPlayer(p)}
                      >
                        <span className="font-medium text-ink">{p.full_name ?? p.gsis_id}</span>
                        <span className="text-caption text-muted">
                          {p.team ?? "—"} · {p.position ?? "—"}
                          {isPinned(p.gsis_id) ? " · pinned" : ""}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            {searchError && <p className="text-body text-warning">{searchError}</p>}
            {pinMessage && <p className="text-body text-warning">{pinMessage}</p>}
            <p className="text-caption text-muted">
              Pin up to {MAX_PINNED_PLAYERS} players to compare
            </p>
            <PinnedPlayersBar />
            <LeagueFilterControl />
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
        "shrink-0 border-t border-line bg-panel p-4 pb-[max(1rem,env(safe-area-inset-bottom))]",
        className,
      )}
    >
      <Button
        type="button"
        className="w-full text-body font-semibold"
        onClick={onExecute}
        disabled={running}
      >
        {running ? "Running…" : "Execute analysis"}
      </Button>
    </div>
  );
}
