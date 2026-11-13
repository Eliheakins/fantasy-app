import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { MAX_PINNED_PLAYERS } from "@/stat/lib/queryUrl";
import type { NFLPlayer } from "@/stat/types/workbench";

export interface PlayerSearchProps {
  query: string;
  setQuery: (v: string) => void;
  debounced: string;
  suggestions: NFLPlayer[];
  isPinned: (gsisId: string) => boolean;
  pinnedCount: number;
  onSelectPlayer: (p: NFLPlayer) => void;
  pinMessage: string | null;
  searchError: string | null;
}

/** Search players by name and pin them to the query (up to MAX_PINNED_PLAYERS). */
export function PlayerSearch({
  query,
  setQuery,
  debounced,
  suggestions,
  isPinned,
  pinnedCount,
  onSelectPlayer,
  pinMessage,
  searchError,
}: PlayerSearchProps) {
  const full = pinnedCount >= MAX_PINNED_PLAYERS;
  return (
    <div className="space-y-2">
      <Input
        type="search"
        aria-label="Search players"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search players by name…"
      />
      {searchError && <p className="text-warning">{searchError}</p>}
      {pinMessage && <p className="text-warning">{pinMessage}</p>}
      {suggestions.length > 0 && debounced.trim().length >= 2 && (
        <ul className="max-h-56 overflow-auto rounded-md border border-line" aria-label="Matching players">
          {suggestions.map((p) => {
            const blocked = isPinned(p.gsis_id) || full;
            return (
              <li key={p.gsis_id}>
                <button
                  type="button"
                  disabled={blocked}
                  onClick={() => void onSelectPlayer(p)}
                  className={cn(
                    "flex min-h-11 w-full flex-col items-start justify-center px-3 py-1.5 text-left hover:bg-panel",
                    blocked && "cursor-not-allowed opacity-50",
                  )}
                >
                  <span className="font-medium text-ink">{p.full_name ?? p.gsis_id}</span>
                  <span className="text-caption text-muted">
                    {p.team ?? "—"} · {p.position ?? "—"}
                    {isPinned(p.gsis_id) ? " · added" : ""}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      <p className="text-caption text-muted">Add up to {MAX_PINNED_PLAYERS} players to look at them side by side.</p>
    </div>
  );
}
