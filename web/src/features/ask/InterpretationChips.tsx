import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useLeagueName } from "@/lib/league";
import { getStatById } from "@/stat/config/statDictionary";
import { statLabel } from "@/stat/lib/queryBuilder";
import { useFilterChipGroups } from "@/features/explore/filterChipGroups";
import { useQueryState } from "@/features/explore/useQueryState";
import type { GranularityMode } from "@/stat/types/queryBuilder";

const GRANULARITY_LABELS: Record<GranularityMode, string> = {
  total: "Total",
  per_game: "Per game",
  per_play: "Per play",
};

const chipClass =
  "inline-flex items-center gap-1 rounded-full border border-border bg-surface px-2.5 py-0.5 text-caption text-text " +
  "transition hover:border-accent disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:border-border";

/**
 * How the question was read, one click from fixed: remove a stat or filter that is wrong, or switch
 * total / per game / per play. Each edit rewrites the URL, so the table follows, and Ask keeps the
 * correction (see `useAsk`). Anything that needs adding is done in Explore.
 */
export function InterpretationChips() {
  const { state, toggleStatId, toggleFilterId, setActiveGranularity } = useQueryState();
  const chipGroups = useFilterChipGroups();
  const filterLabels = new Map(
    chipGroups.flatMap((g) => g.options.map((o): [string, string] => [o.id, `${g.label}: ${o.label}`])),
  );
  const leagueName = useLeagueName();
  const nameOf = (id: string) => {
    const stat = getStatById(id);
    return stat ? statLabel(stat, leagueName) : id;
  };
  const keepsRanking = (id: string) => state.order?.metric === id;

  return (
    <div className="space-y-2" aria-label="How this was read">
      <p className="text-caption font-medium uppercase tracking-wide text-muted">
        How this was read (click × to remove)
      </p>
      <div className="flex flex-wrap gap-1.5">
        {state.stats.map((id) => (
          <button
            key={id}
            type="button"
            className={chipClass}
            disabled={state.stats.length === 1 || keepsRanking(id)}
            onClick={() => toggleStatId(id)}
            aria-label={`Remove ${nameOf(id)}`}
          >
            {nameOf(id)} <span aria-hidden>×</span>
          </button>
        ))}
        {state.filters.map((id) => (
          <button
            key={id}
            type="button"
            className={chipClass}
            onClick={() => toggleFilterId(id)}
            aria-label={`Remove ${filterLabels.get(id) ?? id}`}
          >
            {filterLabels.get(id) ?? id} <span aria-hidden>×</span>
          </button>
        ))}
      </div>
      <ToggleGroup
        type="single"
        size="sm"
        value={state.granularity}
        onValueChange={(value) => {
          if (value === "total" || value === "per_game" || value === "per_play") {
            setActiveGranularity(value);
          }
        }}
        aria-label="Granularity"
        className="justify-start"
      >
        {(Object.keys(GRANULARITY_LABELS) as GranularityMode[]).map((g) => (
          <ToggleGroupItem key={g} value={g}>
            {GRANULARITY_LABELS[g]}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    </div>
  );
}
