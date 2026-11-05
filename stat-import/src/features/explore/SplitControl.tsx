import { ToggleGroup, ToggleGroupItem } from "@/shared/components/ui/toggle-group";
import { useQueryState } from "@/shared/lib/useQueryState";

const NO_SPLIT = "none";

/** One row per player, or per player and season, or per player and week. */
export function SplitControl() {
  const { state, setSplit } = useQueryState();

  return (
    <div className="space-y-1">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Split by</h3>
      <p className="mt-0.5 text-xs text-ink-muted">
        One row per player, or one per season or week. With a ranking, it ranks single seasons or games.
      </p>
      <ToggleGroup
        type="single"
        value={state.split ?? NO_SPLIT}
        onValueChange={(value) => {
          if (value === NO_SPLIT) {
            setSplit(null);
          } else if (value === "season" || value === "week") {
            setSplit(value);
          }
        }}
        className="mt-3 flex flex-wrap gap-2"
        aria-label="Split by"
      >
        <ToggleGroupItem value={NO_SPLIT} className="rounded-md">
          None
        </ToggleGroupItem>
        <ToggleGroupItem value="season" className="rounded-md">
          Season
        </ToggleGroupItem>
        <ToggleGroupItem value="week" className="rounded-md">
          Week
        </ToggleGroupItem>
      </ToggleGroup>
    </div>
  );
}
